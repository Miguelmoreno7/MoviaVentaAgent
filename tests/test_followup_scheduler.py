from types import SimpleNamespace

from movia_sales_agent.chatwoot.client import ChatwootConversation
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.followup.scheduler import FollowUpScheduler, build_followup_message


def followup_settings(**overrides):
    values = {
        "DATABASE_URL": None,
        "OPENAI_API_KEY": None,
        "OPENAI_MODEL": "offline",
        "MOVIA_DISABLE_OPENAI": True,
        "MOVIA_DISABLE_DATABASE": True,
        "MOVIA_FOLLOWUP_ENABLED": True,
        "MOVIA_FOLLOWUP_DELAY_HOURS": 4,
        "MOVIA_FOLLOWUP_SCAN_INTERVAL_SECONDS": 300,
        "MOVIA_FOLLOWUP_WINDOW_SAFETY_MINUTES": 30,
        "MOVIA_FOLLOWUP_MAX_ATTEMPTS": 3,
        "MOVIA_PLATFORM_OBSERVABILITY_ENABLED": False,
        "CHATWOOT_URL": None,
        "CHATWOOT_API_TOKEN": None,
        "CHATWOOT_ACCOUNT_ID": None,
    }
    values.update(overrides)
    return Settings(**values)


def candidate(**overrides):
    values = {
        "lead_id": "lead-1",
        "external_user_id": "5218180000000",
        "channel": "whatsapp",
        "current_stage": "educating",
        "last_action": "answer_and_advance",
        "profile_data": {},
        "trigger_user_message_id": "user-message-1",
    }
    values.update(overrides)
    return values


def test_default_followup_message():
    assert build_followup_message(candidate()) == (
        "Te doy seguimiento por aquí.\n\n"
        "¿Quieres que retomemos la cotización o prefieres que te ayude a elegir la opción correcta para tu negocio?"
    )


def test_close_or_link_followup_message():
    assert build_followup_message(candidate(last_action="direct_close")) == (
        "Te doy seguimiento por aquí.\n\n"
        "¿Pudiste abrir el link o quieres que te guíe con la opción correcta para empezar?"
    )


def test_product_context_followup_message():
    assert build_followup_message(
        candidate(
            profile_data={
                "product_context": {"active_product_context": "movia_hibrido"},
            }
        )
    ) == (
        "Te doy seguimiento por aquí sobre MovIA Híbrido.\n\n"
        "¿Quieres que retomemos la cotización o prefieres que te ayude a confirmar si es la opción correcta para tu negocio?"
    )


def test_scheduler_claims_rechecks_sends_and_saves_message_through_chatwoot():
    repo = FakeFollowUpRepository(candidates=[candidate()])
    chatwoot = FakeChatwootClient()
    scheduler = FollowUpScheduler(
        settings=followup_settings(),
        repository=repo,
        whatsapp_client=FakeWhatsAppClient(),
        chatwoot_client=chatwoot,
    )

    sent_count = scheduler.scan_once()

    assert sent_count == 1
    assert repo.find_calls[0]["delay_hours"] == 4
    assert repo.claims == [{"lead_id": "lead-1", "trigger_user_message_id": "user-message-1"}]
    assert repo.validity_checks == [{"lead_id": "lead-1", "trigger_user_message_id": "user-message-1"}]
    assert repo.saved_messages[0]["external_message_id"] == "followup:attempt-1"
    assert repo.sent_attempts[0]["attempt_id"] == "attempt-1"
    assert chatwoot.public_messages[0]["messages"] == [repo.saved_messages[0]["content"]]


def test_scheduler_skips_claimed_candidate_if_user_replied_before_send():
    repo = FakeFollowUpRepository(candidates=[candidate()], still_valid=False)
    scheduler = FollowUpScheduler(
        settings=followup_settings(),
        repository=repo,
        whatsapp_client=FakeWhatsAppClient(),
        chatwoot_client=FakeChatwootClient(),
    )

    sent_count = scheduler.scan_once()

    assert sent_count == 0
    assert repo.skipped_attempts == [{"attempt_id": "attempt-1", "reason": "followup_skipped_window_expired_or_answered"}]
    assert repo.saved_messages == []


def test_scheduler_falls_back_to_whatsapp_when_chatwoot_is_disabled():
    repo = FakeFollowUpRepository(candidates=[candidate()])
    whatsapp = FakeWhatsAppClient()
    scheduler = FollowUpScheduler(
        settings=followup_settings(),
        repository=repo,
        whatsapp_client=whatsapp,
        chatwoot_client=FakeChatwootClient(enabled=False),
    )

    sent_count = scheduler.scan_once()

    assert sent_count == 1
    assert whatsapp.sent[0]["to"] == "5218180000000"
    assert repo.sent_attempts[0]["send_result"]["transport"] == "whatsapp"


def test_scheduler_records_failed_attempt_without_raising():
    repo = FakeFollowUpRepository(candidates=[candidate()])
    scheduler = FollowUpScheduler(
        settings=followup_settings(),
        repository=repo,
        whatsapp_client=FakeWhatsAppClient(fail=True),
        chatwoot_client=FakeChatwootClient(enabled=False),
    )

    sent_count = scheduler.scan_once()

    assert sent_count == 0
    assert repo.failed_attempts[0]["attempt_id"] == "attempt-1"
    assert "RuntimeError" in repo.failed_attempts[0]["error_text"]


def test_scheduler_skips_when_platform_runtime_disables_agent():
    repo = FakeFollowUpRepository(candidates=[candidate()])
    scheduler = FollowUpScheduler(
        settings=followup_settings(),
        repository=repo,
        whatsapp_client=FakeWhatsAppClient(),
        chatwoot_client=FakeChatwootClient(),
        observability=FakeObservability(enabled=False),
    )

    sent_count = scheduler.scan_once()

    assert sent_count == 0
    assert repo.find_calls == []


class FakeFollowUpRepository:
    enabled = True

    def __init__(self, *, candidates, still_valid=True):
        self.candidates = candidates
        self.still_valid = still_valid
        self.find_calls = []
        self.claims = []
        self.validity_checks = []
        self.saved_messages = []
        self.sent_attempts = []
        self.failed_attempts = []
        self.skipped_attempts = []

    def find_followup_candidates(self, **kwargs):
        self.find_calls.append(kwargs)
        return self.candidates

    def claim_followup_attempt(self, **kwargs):
        self.claims.append(
            {
                "lead_id": kwargs["lead_id"],
                "trigger_user_message_id": kwargs["trigger_user_message_id"],
            }
        )
        return {"id": "attempt-1"}

    def is_followup_still_valid(self, **kwargs):
        self.validity_checks.append(
            {
                "lead_id": kwargs["lead_id"],
                "trigger_user_message_id": kwargs["trigger_user_message_id"],
            }
        )
        return self.still_valid

    def save_message(self, lead_id, role, content, external_message_id=None, retrieval_metadata=None, **_kwargs):
        self.saved_messages.append(
            {
                "lead_id": lead_id,
                "role": role,
                "content": content,
                "external_message_id": external_message_id,
                "retrieval_metadata": retrieval_metadata,
            }
        )

    def mark_followup_sent(self, **kwargs):
        self.sent_attempts.append(kwargs)

    def mark_followup_failed(self, **kwargs):
        self.failed_attempts.append(kwargs)

    def mark_followup_skipped(self, **kwargs):
        self.skipped_attempts.append(kwargs)


class FakeWhatsAppClient:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.sent = []

    def send_text(self, to_number, text):
        if self.fail:
            raise RuntimeError("whatsapp unavailable")
        self.sent.append({"to": to_number, "text": text})
        return {"mocked": True}


class FakeChatwootClient:
    def __init__(self, *, enabled=True):
        self.enabled = enabled
        self.public_messages = []

    def resolve_conversation_for_lead(self, *, lead_id, whatsapp_number):
        return ChatwootConversation(account_id=2, conversation_id=66)

    def send_public_messages(self, conversation, messages):
        self.public_messages.append(
            {"conversation_id": conversation.conversation_id, "messages": list(messages)}
        )
        return {"transport": "chatwoot", "conversation_id": conversation.conversation_id}


class FakeObservability:
    def __init__(self, *, enabled):
        self.enabled = enabled

    def resolve_runtime(self):
        return SimpleNamespace(enabled=self.enabled), None
