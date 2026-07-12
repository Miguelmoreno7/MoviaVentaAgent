from movia_sales_agent.agent.contextual_reply import apply_contextual_reply_resolution
from movia_sales_agent.agent.interaction_context import build_analyzer_interaction_context
from movia_sales_agent.agent.reply_frame import (
    REPLY_FRAME_ACTION_REQUIREMENT,
    REPLY_FRAME_LINK_START_CONFIRMATION,
    ReplyFrameSemanticResolution,
    latest_reply_frame,
    merge_reply_frame_observation,
    reply_frame_for_sales_plan,
    resolve_reply_frame_with_usage,
    should_resolve_reply_frame,
)
from movia_sales_agent.analyzer.contract_v3 import AnalyzerTurnObservation
from movia_sales_agent.contracts.commercial import (
    CTAType,
    Intent,
    MacroAction,
    MicroAction,
    PlannerReasonCode,
    SalesStage,
)
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


def test_planner_reply_frame_preserves_existing_planner_metadata_only():
    plan = SalesPlan(
        macro_action=MacroAction.DISCOVER_NEED,
        micro_action=MicroAction.ASK_ACTION_REQUIREMENT,
        commercial_goal="discover",
        next_question="¿Solo responde o también hace acciones?",
        next_question_key="action_requirement",
        cta_type=CTAType.DISCOVERY_QUESTION,
        target_stage=SalesStage.DISCOVERY,
        reason_code=PlannerReasonCode.ACTION_REQUIREMENT_UNKNOWN,
    )
    frame = reply_frame_for_sales_plan(plan)

    assert frame["type"] == REPLY_FRAME_ACTION_REQUIREMENT
    assert frame["macro_action"] == "discover_need"
    assert frame["micro_action"] == "ask_action_requirement"
    assert frame["next_question_key"] == "action_requirement"
    assert latest_reply_frame(
        [{"role": "assistant", "analysis": {"reply_frame": frame}}]
    ) == frame


def test_reply_frame_resolution_is_relational_and_does_not_mutate_analyzer_facts():
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.UNKNOWN,
        requirement_update_intent="merge",
        requested_agent_actions=[
            {
                "type": "generate_quote",
                "evidence_span": "Cotizar",
                "requirement_strength": "explicit",
            }
        ],
    )
    resolution = ReplyFrameSemanticResolution(
        reply_act="provide_answer",
        evidence_span="Cotizar",
    )

    merged = merge_reply_frame_observation(observation, resolution, "Cotizar")

    assert merged == observation
    assert [item.type for item in merged.requested_agent_actions] == ["generate_quote"]


def test_contextual_prior_reference_is_sparse_even_with_specific_intent_label():
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.ONBOARDING_QUESTION,
        prior_reference={
            "type": "implicit_prior_reference",
            "topic_hint": "explicame mas",
            "evidence_span": "explicame mas",
        },
    )
    frame = {
        "type": "planner_context",
        "next_question_key": "explain_or_price",
        "next_question": "¿Quieres que te explique más o prefieres una cotización?",
    }

    assert should_resolve_reply_frame(frame, observation) is True


def test_contextual_reply_requires_literal_evidence():
    class FakeResponse:
        output_text = """{
          "reply_act": "accept",
          "evidence_span": "claro"
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
        frame={"type": REPLY_FRAME_LINK_START_CONFIRMATION},
        message="Sí",
        observation=AnalyzerTurnObservation(),
    )

    assert resolution is not None
    assert resolution.reply_act == "unclear"
    assert resolution.evidence_span is None


def test_link_reply_frame_uses_normalized_target_product():
    plan = SalesPlan(
        macro_action=MacroAction.RECOMMEND_SOLUTION,
        micro_action=MicroAction.RECOMMEND_MOVIA_CAPTURA,
        commercial_goal="recommend",
        cta_type=CTAType.ASK_PERMISSION_TO_SEND_LINK,
        target_stage=SalesStage.SOLUTION_RECOMMENDED,
        reason_code=PlannerReasonCode.ANSWERS_ONLY_CAPTURA_FIT,
    )
    frame = reply_frame_for_sales_plan(
        plan,
        {"recommended_product": "movia_captura"},
    )

    assert frame["type"] == REPLY_FRAME_LINK_START_CONFIRMATION
    assert frame["target_product"] == "movia_captura"


def test_generic_reply_frame_runs_only_for_sparse_analyzer_output():
    frame = {"type": "planner_context", "next_question_key": "explain_more"}
    assert should_resolve_reply_frame(frame, AnalyzerTurnObservation()) is True
    assert (
        should_resolve_reply_frame(
            frame,
            AnalyzerTurnObservation(primary_intent=Intent.PRICING_QUESTION),
        )
        is False
    )


def test_interaction_context_is_ephemeral_and_contains_previous_planner_state():
    context = build_analyzer_interaction_context(
        lead_profile={
            "current_stage": "solution_recommended",
            "profile_data": {
                "known_product_fit": "movia_hibrido",
                "product_context": {"active_product_context": "movia_hibrido"},
            },
        },
        recent_messages=[
            {
                "role": "assistant",
                "content": "¿Quieres que te pase el link?",
                "analysis": {
                    "reply_frame": {
                        "type": "link_start_confirmation",
                        "macro_action": "soft_close",
                        "micro_action": "ask_permission_to_send_link",
                        "cta_type": "ask_permission_to_send_link",
                        "next_question_key": "link_start_confirmation",
                        "target_product": "movia_hibrido",
                    }
                },
            }
        ],
    )

    assert context["current_interlocutor"] == "movia_salesperson"
    assert context["future_requirement_target"] == "purchased_agent"
    assert context["previous_planner"]["next_question_key"] == "link_start_confirmation"
    assert context["previous_planner"]["target_product"] == "movia_hibrido"
    assert context["commercial_state"]["active_product_context"] == "movia_hibrido"


def test_action_examples_do_not_imply_a_declared_paid_action_count():
    from movia_sales_agent.agent.requirements import active_external_action_count

    assert active_external_action_count(
        {"external_actions": [{"type": "schedule_appointment", "active": True}]}
    ) is None
