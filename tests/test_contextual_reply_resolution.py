from movia_sales_agent.agent.contextual_reply import apply_contextual_reply_resolution
from movia_sales_agent.agent.reply_frame import (
    REPLY_FRAME_ACTION_REQUIREMENT,
    REPLY_FRAME_LINK_START_CONFIRMATION,
    ReplyFrameSemanticResolution,
    latest_reply_frame,
    merge_reply_frame_observation,
    reply_frame_for_sales_plan,
    resolve_reply_frame_with_usage,
)
from movia_sales_agent.analyzer.contract_v3 import AnalyzerTurnObservation
from movia_sales_agent.contracts.commercial import CTAType, MacroAction, MicroAction, PlannerReasonCode, SalesStage
from movia_sales_agent.models.schemas import SalesPlan, TurnAnalysis


def test_legacy_contextual_resolver_is_disabled_and_does_not_mutate_state():
    analysis, normalized = apply_contextual_reply_resolution(
        analysis=TurnAnalysis(),
        normalized_turn={"explicit_start_intent": False},
        message="Sí porfavor",
        recent_messages=[{"role": "assistant", "content": "¿Quieres que te pase el link?"}],
    )

    assert analysis.explicit_start_intent is False
    assert normalized["explicit_start_intent"] is False
    assert normalized["contextual_reply_resolution"]["mode"] == "disabled_in_favor_of_reply_frame_resolver"


def test_planner_reply_frame_is_metadata_not_lead_state():
    plan = SalesPlan(
        macro_action=MacroAction.DISCOVER_NEED,
        micro_action=MicroAction.ASK_ACTION_REQUIREMENT,
        commercial_goal="discover",
        cta_type=CTAType.DISCOVERY_QUESTION,
        target_stage=SalesStage.DISCOVERY,
        reason_code=PlannerReasonCode.ACTION_REQUIREMENT_UNKNOWN,
    )
    assert reply_frame_for_sales_plan(plan) == {"type": REPLY_FRAME_ACTION_REQUIREMENT}
    assert latest_reply_frame([
        {"role": "assistant", "analysis": {"reply_frame": {"type": REPLY_FRAME_ACTION_REQUIREMENT}}}
    ]) == {"type": REPLY_FRAME_ACTION_REQUIREMENT}


def test_reply_frame_resolution_merges_literal_spanish_ontology_actions():
    message = "Cotizar, responder, dar información"
    observation = AnalyzerTurnObservation()
    resolution = ReplyFrameSemanticResolution.model_validate(
        {
            "requested_agent_capabilities": [
                {"type": "answer_customer_questions", "evidence_span": "responder"},
                {"type": "provide_catalog_information", "evidence_span": "dar información"},
            ],
            "requested_agent_actions": [
                {"type": "generate_quote", "evidence_span": "Cotizar"}
            ],
            "action_requirement_selection": "external_actions_required",
            "start_or_link_confirmed": False,
            "confirmation_evidence_span": None,
            "requirement_update_intent": "merge",
        }
    )

    merged = merge_reply_frame_observation(observation, resolution, message)

    assert [item.type for item in merged.requested_agent_actions] == ["generate_quote"]
    assert {item.type for item in merged.requested_agent_capabilities} == {
        "answer_customer_questions", "provide_catalog_information"
    }


def test_reply_frame_resolution_drops_nonliteral_evidence():
    resolution = ReplyFrameSemanticResolution.model_validate(
        {
            "requested_agent_capabilities": [],
            "requested_agent_actions": [{"type": "generate_quote", "evidence_span": "cotización"}],
            "action_requirement_selection": "unknown",
            "start_or_link_confirmed": False,
            "confirmation_evidence_span": None,
            "requirement_update_intent": "no_change",
        }
    )
    merged = merge_reply_frame_observation(AnalyzerTurnObservation(), resolution, "Cotizar")
    assert merged.requested_agent_actions == []


def test_link_reply_frame_is_recognized_from_planner_metadata():
    plan = SalesPlan(
        macro_action=MacroAction.RECOMMEND_SOLUTION,
        micro_action=MicroAction.RECOMMEND_MOVIA_CAPTURA,
        commercial_goal="recommend",
        cta_type=CTAType.ASK_PERMISSION_TO_SEND_LINK,
        target_stage=SalesStage.SOLUTION_RECOMMENDED,
        reason_code=PlannerReasonCode.ANSWERS_ONLY_CAPTURA_FIT,
    )
    assert reply_frame_for_sales_plan(plan) == {
        "type": REPLY_FRAME_LINK_START_CONFIRMATION,
        "product": "movia_captura",
    }


def test_action_examples_do_not_imply_a_declared_paid_action_count():
    from movia_sales_agent.agent.requirements import active_external_action_count

    assert active_external_action_count(
        {"external_actions": [{"type": "schedule_appointment", "active": True}]}
    ) is None


def test_reply_frame_resolver_uses_strict_schema_and_sanitizes_output():
    class FakeResponse:
        output_text = """{
          \"requested_agent_capabilities\": [],
          \"requested_agent_actions\": [{\"type\": \"generate_quote\", \"evidence_span\": \"Cotizar\", \"requirement_strength\": \"explicit\"}],
          \"action_requirement_selection\": \"external_actions_required\",
          \"start_or_link_confirmed\": false,
          \"confirmation_evidence_span\": null,
          \"requirement_update_intent\": \"merge\"
        }"""
        usage = None

    class FakeClient:
        class responses:
            @staticmethod
            def create(**_kwargs):
                return FakeResponse()

    class FakeService:
        enabled = True
        client = FakeClient()

        class settings:
            analysis_model = "test-model"

    resolution, _usage = resolve_reply_frame_with_usage(
        FakeService(),
        frame={"type": REPLY_FRAME_ACTION_REQUIREMENT},
        message="Cotizar",
    )
    assert resolution is not None
    assert resolution.requested_agent_actions[0].type == "generate_quote"
