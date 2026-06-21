from movia_sales_agent.contracts.commercial import MacroAction, ProductFit
from movia_sales_agent.evaluation.models import ValidationScenario, ValidationTurn
from movia_sales_agent.evaluation.scoring import score_turn
from movia_sales_agent.models.schemas import ChatResponse, TurnAnalysis


def make_response(
    *,
    user: str = "Tengo muchos mensajes.",
    response_text: str = "Va, ¿qué necesitas que haga el agente?",
    action: str = MacroAction.ANSWER_AND_ADVANCE.value,
    normalized_turn=None,
    profile_data=None,
    selected_action=None,
) -> ChatResponse:
    selected = {
        "macro_action": action,
        "micro_action": "answer_general_then_discover_need",
        "cta_type": "soft_question",
        "objection_flow_step": "none",
    }
    selected.update(selected_action or {})
    return ChatResponse(
        action=action,
        response=response_text,
        response_messages=[response_text],
        analysis=TurnAnalysis(),
        lead_state={"profile_data": profile_data or {}},
        selected_action=selected,
        response_metadata={"normalized_turn": normalized_turn or {}},
    )


def score_names(response: ChatResponse, *, user: str, history=None):
    metrics, failures = score_turn(
        validation_turn=ValidationTurn(turn_id=2, user=user, ideal_assistant="", expected={}),
        response=response,
        source_capabilities=set(),
        ground_truth={"products": [], "official_links": []},
        scenario=ValidationScenario(
            conversation_id="SEMANTIC-METRIC-TEST",
            persona="test",
            difficulty="unit",
            success_goal="semantic metrics",
        ),
        user_history=history or [],
        scenario_business_terms={},
    )
    assert failures == []
    return {metric.name: metric for metric in metrics}


def test_problem_capability_leakage_metric_fails():
    metrics = score_names(
        make_response(
            normalized_turn={
                "observed_business_problems": ["high_message_volume"],
                "requested_agent_capabilities": ["answer_customer_questions"],
            }
        ),
        user="Tengo muchos mensajes de WhatsApp.",
    )

    assert metrics["semantic.problem_capability_leakage"].status == "failed"


def test_current_question_future_capability_leakage_metric_fails():
    metrics = score_names(
        make_response(
            normalized_turn={
                "requested_agent_capabilities": ["provide_prices"],
            }
        ),
        user="¿Cuánto cuesta Captura?",
    )

    assert metrics["semantic.current_question_future_capability_leakage"].status == "failed"


def test_requirement_profile_reset_metric_fails():
    metrics = score_names(
        make_response(profile_data={"requirement_profile": {"external_actions": []}}),
        user="Son como cinco acciones.",
        history=["Necesito que el agente cotice y registre pedidos en mi sistema."],
    )

    assert metrics["semantic.requirement_profile_reset"].status == "failed"


def test_premature_product_recommendation_metric_fails():
    metrics = score_names(
        make_response(
            response_text="Te conviene MovIA Captura.",
            action=MacroAction.RECOMMEND_SOLUTION.value,
            normalized_turn={"requirement_class": "unknown"},
        ),
        user="Tengo muchos WhatsApps.",
    )

    assert metrics["semantic.premature_product_recommendation"].status == "failed"


def test_sales_capability_misrouted_metric_fails():
    metrics = score_names(
        make_response(
            profile_data={
                "known_product_fit": ProductFit.MOVIA_CAPTURA.value,
                "requirement_profile": {
                    "sales_capabilities": [{"type": "close_sale", "active": True}]
                },
            }
        ),
        user="Quiero que el agente cierre ventas.",
    )

    assert metrics["semantic.sales_capability_misrouted"].status == "failed"


def test_external_action_scope_miss_metric_fails():
    metrics = score_names(
        make_response(
            normalized_turn={
                "requested_agent_actions": ["generate_quote", "write_external_system"],
                "scope_flags": [],
            },
            profile_data={
                "known_product_fit": ProductFit.MOVIA_HIBRIDO.value,
                "requirement_profile": {
                    "external_actions": [{"type": "generate_quote", "active": True}],
                    "declared_external_action_count": {"value": 5, "active": True},
                },
            },
        ),
        user="Necesito que cotice y registre pedidos en mi sistema.",
    )

    assert metrics["semantic.external_action_scope_miss"].status == "failed"


def test_wrong_product_direct_close_metric_fails():
    metrics = score_names(
        make_response(
            response_text="Empieza en app.moviatech.com.mx.",
            action=MacroAction.DIRECT_CLOSE.value,
            selected_action={"cta_type": "direct_close"},
            profile_data={
                "known_product_fit": ProductFit.MOVIA_HIBRIDO.value,
                "confirmed_product": ProductFit.MOVIA_CAPTURA.value,
            },
        ),
        user="Pásame el link.",
    )

    assert metrics["semantic.wrong_product_direct_close"].status == "failed"


def test_unsupported_standard_scope_claim_metric_fails():
    metrics = score_names(
        make_response(
            response_text="Te conviene MovIA Híbrido para cubrir esas cinco acciones.",
            normalized_turn={"scope_flags": ["custom_scope_review_required"]},
            profile_data={"known_product_fit": ProductFit.CUSTOM_REVIEW.value},
        ),
        user="Son como cinco acciones.",
    )

    assert metrics["semantic.unsupported_standard_scope_claim"].status == "failed"
