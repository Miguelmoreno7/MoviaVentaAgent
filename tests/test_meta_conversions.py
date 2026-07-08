from types import SimpleNamespace

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.db.repository import MoviaRepository
from movia_sales_agent.meta.conversions import (
    MetaConversionsService,
    applicable_event_names,
    build_conversion_events,
    hashed_phone_from_lead_state,
)
from movia_sales_agent.meta.cli import create_dataset
from movia_sales_agent.whatsapp.client import WhatsAppClient


def meta_settings(**overrides):
    values = {
        "DATABASE_URL": None,
        "OPENAI_API_KEY": None,
        "OPENAI_MODEL": "offline",
        "MOVIA_DISABLE_OPENAI": True,
        "MOVIA_DISABLE_DATABASE": True,
        "META_WHATSAPP_ACCESS_TOKEN": "token",
        "META_WHATSAPP_PHONE_NUMBER_ID": "phone-id",
        "META_WHATSAPP_BUSINESS_ACCOUNT_ID": "waba-id",
        "META_CAPI_DATASET_ID": "dataset-id",
    }
    values.update(overrides)
    return Settings(**values)


def fake_response(**overrides):
    values = {
        "lead_id": "lead-1",
        "action": "answer_and_advance",
        "analysis": {
            "primary_intent": "ask_price",
            "topics": ["pricing"],
            "buying_signal": "low",
            "explicit_start_intent": False,
        },
        "selected_action": {
            "macro_action": "answer_and_advance",
            "micro_action": "answer_price",
            "cta_type": "ask_discovery_question",
            "target_stage": "educating",
        },
        "knowledge_plan": {"knowledge_needs": ["product_pricing"]},
        "lead_state": {"current_stage": "educating"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_parser_extracts_ctwa_clid_from_native_meta_referral_payload():
    client = WhatsAppClient(meta_settings())

    messages = client.parse_messages(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "wamid.1",
                                        "from": "5218180000000",
                                        "type": "text",
                                        "timestamp": "1782168061",
                                        "text": {"body": "Hola"},
                                        "referral": {
                                            "ctwa_clid": "ctwa-123",
                                            "campaign_id": "camp-1",
                                            "source_url": "https://fb.me/ad",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )

    assert len(messages) == 1
    assert messages[0].ctwa_clid == "ctwa-123"
    assert messages[0].referral["campaign_id"] == "camp-1"
    assert messages[0].timestamp == "1782168061"


def test_parser_accepts_wrapped_payload_without_ctwa_clid():
    client = WhatsAppClient(meta_settings())

    messages = client.parse_messages(
        [
            {
                "body": {
                    "messages": [
                        {
                            "id": "wamid.n8n.1",
                            "from": "5218717876121",
                            "type": "text",
                            "text": {"body": "Hola"},
                        }
                    ]
                }
            }
        ]
    )

    assert len(messages) == 1
    assert messages[0].ctwa_clid is None
    assert messages[0].text == "Hola"


def test_event_policy_uses_existing_runtime_signals_for_funnel_events():
    response = fake_response(
        analysis={
            "primary_intent": "start_project",
            "topics": ["pricing", "platform_process"],
            "buying_signal": "explicit_start",
            "explicit_start_intent": True,
        },
        selected_action={
            "macro_action": "direct_close",
            "micro_action": "send_app_link_and_deposit_step",
            "cta_type": "send_app_link",
            "target_stage": "closing",
        },
        knowledge_plan={"knowledge_needs": ["product_pricing", "official_policy", "platform_steps"]},
    )

    assert applicable_event_names(response) == [
        "LeadSubmitted",
        "ViewContent",
        "QualifiedLead",
        "InitiateCheckout",
    ]


def test_build_conversion_event_payload_contains_business_messaging_fields():
    events = build_conversion_events(
        fake_response(lead_state={"current_stage": "educating", "external_user_id": "5218180000000"}),
        settings=meta_settings(),
        ctwa_clid="ctwa-123",
    )

    event = events[0]
    assert event.event_name == "LeadSubmitted"
    assert event.payload["action_source"] == "business_messaging"
    assert event.payload["messaging_channel"] == "whatsapp"
    assert event.payload["user_data"]["ctwa_clid"] == "ctwa-123"
    assert event.payload["user_data"]["whatsapp_business_account_id"] == "waba-id"
    assert event.payload["user_data"]["ph"] == [
        hashed_phone_from_lead_state({"external_user_id": "5218180000000"})
    ]
    assert "buying_signal" in event.payload["custom_data"]
    assert None not in event.payload["custom_data"].values()


def test_offline_repository_stores_attribution_once_and_dedupes_events():
    repository = MoviaRepository(meta_settings(MOVIA_DISABLE_DATABASE=True))
    lead = repository.upsert_lead("whatsapp", "5218180000000")

    assert repository.store_meta_ctwa_attribution(lead["id"], "ctwa-1", {"campaign_id": "c1"})
    assert not repository.store_meta_ctwa_attribution(lead["id"], "ctwa-2", {"campaign_id": "c2"})
    assert repository.get_meta_ctwa_attribution(lead["id"])["ctwa_clid"] == "ctwa-1"
    assert repository.create_meta_conversion_event(
        lead_id=lead["id"],
        event_name="LeadSubmitted",
        event_id="event-1",
        payload={"event_name": "LeadSubmitted"},
    )
    assert not repository.create_meta_conversion_event(
        lead_id=lead["id"],
        event_name="LeadSubmitted",
        event_id="event-2",
        payload={"event_name": "LeadSubmitted"},
    )


def test_service_skips_sending_when_dataset_is_missing():
    settings = meta_settings(META_CAPI_DATASET_ID=None)
    repository = MoviaRepository(settings)
    lead = repository.upsert_lead("whatsapp", "5218180000000")
    repository.store_meta_ctwa_attribution(lead["id"], "ctwa-1")
    sender = RecordingMetaClient(configured=False)
    service = MetaConversionsService(settings=settings, repository=repository, client=sender)

    service._record_and_send_response_events(
        response=fake_response(lead_id=lead["id"]),
        latest_ctwa_clid=None,
        latest_referral={},
    )

    assert sender.sent == []


def test_service_records_failed_send_without_raising():
    settings = meta_settings()
    repository = MoviaRepository(settings)
    lead = repository.upsert_lead("whatsapp", "5218180000000")
    repository.store_meta_ctwa_attribution(lead["id"], "ctwa-1")
    sender = RecordingMetaClient(configured=True, fail=True)
    service = MetaConversionsService(settings=settings, repository=repository, client=sender)

    service._record_and_send_response_events(
        response=fake_response(lead_id=lead["id"]),
        latest_ctwa_clid=None,
        latest_referral={},
    )

    assert sender.sent


def test_dataset_cli_create_uses_waba_dataset_endpoint(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "dataset-id"}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def request(self, method, url, headers, json):
            calls.append({"method": method, "url": url, "headers": headers, "json": json})
            return FakeResponse()

    import movia_sales_agent.meta.cli as cli

    monkeypatch.setattr(cli.httpx, "Client", FakeClient)

    result = create_dataset(meta_settings(), "MovIA WhatsApp Leads")

    assert result == {"id": "dataset-id"}
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"].endswith("/waba-id/dataset")
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["json"] == {"name": "MovIA WhatsApp Leads"}


class RecordingMetaClient:
    def __init__(self, *, configured: bool, fail: bool = False):
        self._configured = configured
        self.fail = fail
        self.sent = []

    @property
    def configured(self):
        return self._configured

    def send_event(self, payload):
        self.sent.append(payload)
        if self.fail:
            raise RuntimeError("meta unavailable")
        return {"events_received": 1}
