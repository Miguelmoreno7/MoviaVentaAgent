from __future__ import annotations

from typing import Any, Dict, Optional

from langgraph.graph import END, StateGraph

from movia_sales_agent.analyzer.contract_v3 import ANALYZER_CONTRACT_VERSION, AnalyzerTurnObservation
from movia_sales_agent.analyzer.normalizer import (
    normalize_analyzer_turn,
    normalized_turn_to_analysis,
)
from movia_sales_agent.analyzer.shadow_parser import ShadowSignalParser
from movia_sales_agent.agent.commercial_state import resolve_product_context
from movia_sales_agent.agent.contextual_reply import apply_contextual_reply_resolution
from movia_sales_agent.agent.fulfillment import build_response_fulfillment_policy
from movia_sales_agent.agent.memory import (
    build_structured_memory,
    memory_updates_for_profile,
    merge_lead_profile_memory,
    retrieve_conversation_memory,
    sanitize_response_memory,
)
from movia_sales_agent.agent.objections import ObjectionFlowService
from movia_sales_agent.agent.planners import KnowledgePlanner, SalesPolicyPlanner
from movia_sales_agent.agent.requirements import (
    build_requirement_summary,
    current_turn_requirement_delta,
    derive_action_requirement,
    derive_product_fit,
    derive_scope_flags,
    ensure_requirement_profile,
    merge_requirement_profile,
)
from movia_sales_agent.agent.rag_policy import build_rag_route
from movia_sales_agent.agent.response import (
    BASE_SYSTEM_PROMPT,
    build_generation_context,
    fallback_response,
    response_package_token_estimates,
)
from movia_sales_agent.agent.stages import SalesStageTransitionService
from movia_sales_agent.config.knowledge import load_config_bundle
from movia_sales_agent.config.settings import Settings, get_settings
from movia_sales_agent.db.repository import MoviaRepository
from movia_sales_agent.memory.store import MemoryStore
from movia_sales_agent.models.schemas import AgentState, ChatResponse
from movia_sales_agent.runtime.metadata import (
    compact_response_metadata,
    compact_retrieval_metadata,
    compact_token_usage,
)
from movia_sales_agent.services.openai_service import OpenAIService
from movia_sales_agent.services.openai_service import empty_usage
from movia_sales_agent.services.purchase_status import PurchaseStatusService
from movia_sales_agent.services.rag import RagService
from movia_sales_agent.whatsapp.formatting import split_whatsapp_messages


class MoviaSalesAgent:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        purchase_status_service: Optional[PurchaseStatusService] = None,
    ):
        self.settings = settings or get_settings()
        self.repository = MoviaRepository(self.settings)
        self.memory = MemoryStore(self.settings)
        self.openai_service = OpenAIService(self.settings)
        self.rag_service = RagService(self.repository, self.openai_service, self.memory)
        self.purchase_status_service = purchase_status_service or PurchaseStatusService()
        self.sales_planner = SalesPolicyPlanner()
        self.stage_service = SalesStageTransitionService()
        self.objection_service = ObjectionFlowService()
        self.knowledge_planner = KnowledgePlanner()
        self.shadow_parser = ShadowSignalParser()
        self.config_bundle = load_config_bundle()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("load_memory", self.load_memory)
        workflow.add_node("parse_explicit_signals_shadow", self.parse_explicit_signals_shadow)
        workflow.add_node("analyze_turn", self.analyze_turn)
        workflow.add_node("normalize_and_derive_turn", self.normalize_and_derive_turn)
        workflow.add_node("update_lead_state", self.update_lead_state)
        workflow.add_node("resolve_purchase_status", self.resolve_purchase_status)
        workflow.add_node("sales_policy_planner", self.sales_policy_planner_node)
        workflow.add_node("stage_transition", self.stage_transition_node)
        workflow.add_node("objection_flow", self.objection_flow_node)
        workflow.add_node("response_fulfillment_policy", self.response_fulfillment_policy_node)
        workflow.add_node("knowledge_planner", self.knowledge_planner_node)
        workflow.add_node("fetch_structured_data", self.fetch_structured_data)
        workflow.add_node("fetch_json_playbooks", self.fetch_json_playbooks)
        workflow.add_node("fetch_rag_context", self.fetch_rag_context)
        workflow.add_node("retrieve_conversation_memory", self.retrieve_conversation_memory_node)
        workflow.add_node("merge_context", self.merge_context)
        workflow.add_node("generate_response", self.generate_response)
        workflow.add_node("save_memory", self.save_memory)

        workflow.set_entry_point("load_memory")
        workflow.add_edge("load_memory", "parse_explicit_signals_shadow")
        workflow.add_edge("parse_explicit_signals_shadow", "analyze_turn")
        workflow.add_edge("analyze_turn", "normalize_and_derive_turn")
        workflow.add_edge("normalize_and_derive_turn", "update_lead_state")
        workflow.add_edge("update_lead_state", "resolve_purchase_status")
        workflow.add_edge("resolve_purchase_status", "sales_policy_planner")
        workflow.add_edge("sales_policy_planner", "stage_transition")
        workflow.add_edge("stage_transition", "objection_flow")
        workflow.add_edge("objection_flow", "response_fulfillment_policy")
        workflow.add_edge("response_fulfillment_policy", "knowledge_planner")
        workflow.add_edge("knowledge_planner", "fetch_structured_data")
        workflow.add_edge("fetch_structured_data", "fetch_json_playbooks")
        workflow.add_edge("fetch_json_playbooks", "fetch_rag_context")
        workflow.add_edge("fetch_rag_context", "retrieve_conversation_memory")
        workflow.add_edge("retrieve_conversation_memory", "merge_context")
        workflow.add_edge("merge_context", "generate_response")
        workflow.add_edge("generate_response", "save_memory")
        workflow.add_edge("save_memory", END)
        return workflow.compile()

    def invoke(
        self,
        message: str,
        lead_external_id: str = "local",
        channel: str = "local",
        external_message_id: Optional[str] = None,
    ) -> ChatResponse:
        result = self.graph.invoke(
            {
                "message": message,
                "channel": channel,
                "external_user_id": lead_external_id,
                "external_message_id": external_message_id,
            }
        )
        return ChatResponse(
            lead_id=result.get("lead_id"),
            action=result["sales_plan"].macro_action,
            response=result["response"],
            response_messages=result.get("response_messages", []),
            analysis=result["analysis"],
            retrieval_metadata=result.get("retrieval_metadata", {}),
            lead_state=_lead_state_for_response(result),
            selected_action=result["sales_plan"].model_dump(),
            knowledge_plan=result["knowledge_plan"].model_dump(),
            retrieved_sources=_retrieved_sources_for_response(result.get("rag_context", [])),
            response_metadata=result.get("response_metadata", {}),
            token_usage=result.get("token_usage", {}),
        )

    def load_memory(self, state: AgentState) -> Dict[str, Any]:
        lead = self.repository.upsert_lead(state["channel"], state["external_user_id"])
        lead_id = str(lead["id"]) if lead.get("id") else None
        memory_key = f"{state['channel']}:{state['external_user_id']}"
        recent_messages = self.repository.load_recent_messages(lead_id)
        if not recent_messages:
            recent_messages = self.memory.recent(memory_key)
        return {
            "lead_id": lead_id,
            "lead_profile": lead,
            "recent_messages": recent_messages,
        }

    def parse_explicit_signals_shadow(self, state: AgentState) -> Dict[str, Any]:
        result = self.shadow_parser.parse(state["message"])
        return {"shadow_parser": result.model_dump()}

    def analyze_turn(self, state: AgentState) -> Dict[str, Any]:
        analysis, usage, observation = self.openai_service.analyze_turn_v3_with_usage(
            state["message"], state.get("recent_messages", [])
        )
        return {
            "analysis": analysis,
            "analyzer_observation": observation.model_dump(),
            "token_usage": merge_usage(state.get("token_usage", {}), usage),
        }

    def normalize_and_derive_turn(self, state: AgentState) -> Dict[str, Any]:
        observation = AnalyzerTurnObservation.model_validate(state["analyzer_observation"])
        normalized = normalize_analyzer_turn(
            observation,
            message=state["message"],
            lead_profile=state.get("lead_profile", {}),
            shadow_parser=state.get("shadow_parser", {}),
        )
        analysis = normalized_turn_to_analysis(
            observation,
            normalized,
            message=state["message"],
        )
        analysis, normalized_turn = apply_contextual_reply_resolution(
            analysis=analysis,
            normalized_turn=normalized.model_dump(),
            message=state["message"],
            recent_messages=state.get("recent_messages", []),
        )
        return {
            "analysis": analysis,
            "normalized_turn": normalized_turn,
        }

    def update_lead_state(self, state: AgentState) -> Dict[str, Any]:
        profile_data = dict((state.get("lead_profile", {}) or {}).get("profile_data") or {})
        existing_requirement_profile = ensure_requirement_profile(profile_data)
        delta = current_turn_requirement_delta(
            normalized_turn=state.get("normalized_turn", {}),
            analyzer_observation=state.get("analyzer_observation", {}),
            message=state["message"],
            existing_profile=existing_requirement_profile,
        )
        turn_number = int(existing_requirement_profile.get("last_updated_turn") or 0) + 1
        merged_requirement_profile = merge_requirement_profile(
            existing_requirement_profile,
            delta,
            turn_number=turn_number,
        )
        requirement_summary = build_requirement_summary(
            merged_requirement_profile,
            requested_product=state.get("normalized_turn", {}).get("requested_product"),
        )
        profile_updates = dict(state["analysis"].lead_updates.profile_data or {})
        profile_updates["requirement_profile"] = merged_requirement_profile
        derived_action_requirement = derive_action_requirement(
            merged_requirement_profile.get("requirement_class")
        )
        derived_product_fit = derive_product_fit(merged_requirement_profile)
        product_context = resolve_product_context(
            profile_data=profile_data,
            normalized_turn=state.get("normalized_turn", {}),
            turn_number=turn_number,
        )
        if derived_action_requirement != "unknown":
            profile_updates["action_requirement"] = derived_action_requirement
        else:
            profile_updates.pop("action_requirement", None)
        committed_product = (
            product_context.get("confirmed_product")
            or product_context.get("selected_product")
        )
        if derived_product_fit != "unknown":
            profile_updates["known_product_fit"] = derived_product_fit
        elif committed_product in {"movia_captura", "movia_hibrido"}:
            profile_updates["known_product_fit"] = committed_product
        else:
            profile_updates.pop("known_product_fit", None)
        profile_updates["product_context"] = product_context
        if product_context.get("selected_product"):
            profile_updates["selected_product"] = product_context["selected_product"]
        if product_context.get("confirmed_product"):
            profile_updates["confirmed_product"] = product_context["confirmed_product"]
        state["analysis"].lead_updates.profile_data = profile_updates

        structured_memory = build_structured_memory(
            state["analysis"], state.get("lead_profile", {})
        )
        updates = memory_updates_for_profile(state["analysis"], structured_memory)
        self.repository.update_lead_profile(state.get("lead_id"), updates)
        normalized_turn = dict(state.get("normalized_turn", {}) or {})
        normalized_turn.update(
            {
                "current_turn_requirement_delta": delta,
                "requirement_profile": merged_requirement_profile,
                "requirement_class": merged_requirement_profile.get("requirement_class"),
                "recommended_product": derived_product_fit if derived_product_fit != "unknown" else None,
                "referenced_product": product_context.get("referenced_product"),
                "active_product_context": product_context.get("active_product_context"),
                "product_context": product_context,
                "confirmed_product": profile_updates.get("confirmed_product"),
                "selected_product": profile_updates.get("selected_product")
                or normalized_turn.get("selected_product"),
                "scope_flags": derive_scope_flags(
                    merged_requirement_profile,
                    requested_product=normalized_turn.get("requested_product"),
                ),
                "unsupported_scope": "unsupported_scope"
                in requirement_summary["scope_flags"],
                "custom_scope_review_required": "custom_scope_review_required"
                in requirement_summary["scope_flags"],
                "product_unavailable": "product_unavailable" in requirement_summary["scope_flags"],
                "action_requirement": derived_action_requirement,
            }
        )
        return {
            "structured_memory": structured_memory,
            "lead_profile": merge_lead_profile_memory(
                state.get("lead_profile", {}),
                state["analysis"],
                structured_memory,
            ),
            "normalized_turn": normalized_turn,
        }

    def resolve_purchase_status(self, state: AgentState) -> Dict[str, Any]:
        if not state["analysis"].is_post_purchase:
            return {"purchase_status": {}}
        status = self.purchase_status_service.get_purchase_status(
            channel=state["channel"],
            external_user_id=state["external_user_id"],
            lead_profile=state.get("lead_profile", {}),
        )
        return {"purchase_status": status.model_dump()}

    def sales_policy_planner_node(self, state: AgentState) -> Dict[str, Any]:
        lead_profile = state.get("lead_profile", {})
        sales_plan = self.sales_planner.plan(
            state["analysis"],
            lead_profile,
            current_stage=lead_profile.get("current_stage"),
            previous_stage=lead_profile.get("previous_stage"),
            active_objection=lead_profile.get("active_objection"),
            last_macro_action=lead_profile.get("last_action"),
            normalized_turn=state.get("normalized_turn", {}),
            purchase_status=state.get("purchase_status", {}),
            message=state["message"],
        )
        return {"sales_plan": sales_plan}

    def stage_transition_node(self, state: AgentState) -> Dict[str, Any]:
        stage_transition = self.stage_service.transition(
            lead_profile=state.get("lead_profile", {}),
            analysis=state["analysis"],
            sales_plan=state["sales_plan"],
        )
        return {"stage_transition": stage_transition}

    def objection_flow_node(self, state: AgentState) -> Dict[str, Any]:
        active_objection = self.objection_service.transition(
            lead_profile=state.get("lead_profile", {}),
            analysis=state["analysis"],
            sales_plan=state["sales_plan"],
            stage_transition=state["stage_transition"],
            message=state["message"],
        )
        return {"active_objection": active_objection}

    def response_fulfillment_policy_node(self, state: AgentState) -> Dict[str, Any]:
        policy = build_response_fulfillment_policy(
            analysis=state["analysis"],
            sales_plan=state["sales_plan"],
            normalized_turn=state.get("normalized_turn", {}),
            active_objection=state.get("active_objection").model_dump()
            if state.get("active_objection")
            else state.get("lead_profile", {}).get("active_objection"),
        )
        return {"response_fulfillment_policy": policy}

    def knowledge_planner_node(self, state: AgentState) -> Dict[str, Any]:
        knowledge_plan = self.knowledge_planner.plan(
            state["analysis"],
            state["sales_plan"],
            state["message"],
            active_objection=state.get("active_objection").model_dump()
            if state.get("active_objection")
            else None,
            normalized_turn=state.get("normalized_turn", {}),
            lead_profile=state.get("lead_profile", {}),
            response_fulfillment_policy=state.get("response_fulfillment_policy", {}),
        )
        return {"knowledge_plan": knowledge_plan}

    def fetch_structured_data(self, state: AgentState) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        sources = state["knowledge_plan"].structured_sources
        if "postgres.products" in sources:
            context["products"] = self.repository.fetch_products()
        if "postgres.policies" in sources:
            context["policies"] = self.repository.fetch_policies()
        if "postgres.official_links" in sources:
            context.update(self.repository.fetch_platform_context())
        return {"structured_context": context}

    def fetch_json_playbooks(self, state: AgentState) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        for source in state["knowledge_plan"].json_sources:
            if source.startswith("objection_playbook:"):
                objection_type = source.split(":", 1)[1]
                context["objection_playbook"] = _single_objection_playbook(
                    self.config_bundle.get("objection_playbook") or {},
                    objection_type,
                )
                continue
            if source in self.config_bundle:
                context[source] = self.config_bundle[source]
        return {"json_context": context}

    def fetch_rag_context(self, state: AgentState) -> Dict[str, Any]:
        metadata_filter = state["knowledge_plan"].rag_metadata_filter
        rag_context, usage = self.rag_service.retrieve_with_usage(
            state["knowledge_plan"].rag_queries,
            metadata_filter=metadata_filter,
        )
        return {
            "rag_context": rag_context,
            "token_usage": merge_usage(state.get("token_usage", {}), usage),
        }

    def retrieve_conversation_memory_node(self, state: AgentState) -> Dict[str, Any]:
        evidence = retrieve_conversation_memory(
            state["analysis"],
            state.get("recent_messages", []),
        )
        return {"conversation_memory_evidence": evidence}

    def merge_context(self, state: AgentState) -> Dict[str, Any]:
        merged = build_generation_context(
            state["analysis"],
            state["sales_plan"],
            state.get("structured_context", {}),
            state.get("json_context", {}),
            state.get("rag_context", []),
            state.get("recent_messages", []),
            lead_profile=state.get("lead_profile", {}),
            stage_transition=state.get("stage_transition"),
            active_objection=state.get("active_objection"),
            structured_memory=state.get("structured_memory", {}),
            conversation_memory_evidence=state.get("conversation_memory_evidence", []),
            normalized_turn=state.get("normalized_turn", {}),
            response_fulfillment_policy=state.get("response_fulfillment_policy", {}),
            purchase_status=state.get("purchase_status", {}),
        )
        retrieval_metadata = {
            "structured_sources": state["knowledge_plan"].structured_sources,
            "json_sources": state["knowledge_plan"].json_sources,
            "rag_routing_reason": state["knowledge_plan"].rag_routing_reason,
            "rag_metadata_filter": state["knowledge_plan"].rag_metadata_filter,
            "rag_chunk_count": len(state.get("rag_context", [])),
            "retrieved_sources": _retrieved_sources_for_response(state.get("rag_context", [])),
            "conversation_memory_lookup": "used"
            if state["analysis"].references_prior_message
            else "skipped",
            "conversation_memory_evidence": state.get("conversation_memory_evidence", []),
            "response_fulfillment_policy": state.get("response_fulfillment_policy", {}),
            "purchase_status": state.get("purchase_status", {}),
        }
        return {"merged_context": merged, "retrieval_metadata": retrieval_metadata}

    def generate_response(self, state: AgentState) -> Dict[str, Any]:
        package_estimates = response_package_token_estimates(
            state["merged_context"],
            BASE_SYSTEM_PROMPT,
            state["message"],
        )
        deterministic_response = should_use_deterministic_response(state)
        if deterministic_response:
            response = fallback_response(
                state["message"],
                state["analysis"],
                state["sales_plan"],
                state["merged_context"],
            )
            usage = empty_usage("response", self.settings.response_model, "deterministic")
        else:
            response, usage = self.openai_service.generate_response_with_usage(
                BASE_SYSTEM_PROMPT,
                state["message"],
                state["merged_context"],
            )
        usage = attach_usage_details(usage, "response_package_estimates", package_estimates)
        response_source = "deterministic" if deterministic_response else ("openai" if response else "fallback")
        if not response:
            response = fallback_response(
                state["message"],
                state["analysis"],
                state["sales_plan"],
                state["merged_context"],
            )
        response, memory_validation = sanitize_response_memory(response, state["merged_context"])
        response_messages = split_whatsapp_messages(response)
        token_usage = merge_usage(state.get("token_usage", {}), usage)
        response_metadata = {
            "analyzer_contract_version": ANALYZER_CONTRACT_VERSION,
            "analyzer_observation": state.get("analyzer_observation", {}),
            "normalized_turn": state.get("normalized_turn", {}),
            "parser_llm_telemetry": (state.get("normalized_turn", {}) or {}).get("parser_llm_telemetry", {}),
            "shadow_parser": state.get("shadow_parser", {}),
            "response_source": response_source,
            "message_count": len(response_messages),
            "message_lengths": [len(message) for message in response_messages],
            "analysis_model": self.settings.analysis_model,
            "response_model": self.settings.response_model,
            "embedding_model": self.settings.openai_embedding_model,
            "structured_context_keys": sorted(state.get("structured_context", {}).keys()),
            "json_context_keys": sorted(state.get("json_context", {}).keys()),
            "response_package_token_estimates": package_estimates,
            "claim_constraints": state["merged_context"].get("claim_constraints", {}),
            "response_fulfillment_policy": state.get("response_fulfillment_policy", {}),
            "purchase_status": state.get("purchase_status", {}),
            "memory_validation": memory_validation,
        }
        return {
            "response": response,
            "response_messages": response_messages,
            "token_usage": token_usage,
            "response_metadata": response_metadata,
        }

    def save_memory(self, state: AgentState) -> Dict[str, Any]:
        memory_key = f"{state['channel']}:{state['external_user_id']}"
        self.repository.save_message(
            state.get("lead_id"),
            "user",
            state["message"],
            external_message_id=state.get("external_message_id"),
            analysis=state["analysis"].model_dump(),
        )
        self.repository.save_message(
            state.get("lead_id"),
            "assistant",
            state["response"],
            retrieval_metadata=self._stored_retrieval_metadata(state),
            token_usage=self._stored_token_usage(state),
        )
        self.memory.add_recent(
            memory_key,
            {
                "role": "user",
                "content": state["message"],
                "analysis": state["analysis"].model_dump(),
            },
        )
        self.memory.add_recent(memory_key, {"role": "assistant", "content": state["response"]})
        stage_transition = state["stage_transition"]
        self.repository.update_lead_profile(
            state.get("lead_id"),
            {},
            current_stage=stage_transition.current_stage,
            previous_stage=stage_transition.previous_stage,
            stage_before_objection=stage_transition.stage_before_objection,
            stage_reason_code=stage_transition.stage_reason_code,
            stage_reason=stage_transition.stage_reason,
            conversation_mode=stage_transition.conversation_mode,
            stage_changed=stage_transition.stage_changed,
            active_objection=state["active_objection"].model_dump(),
            last_action=state["sales_plan"].macro_action,
        )
        return {}

    def _stored_retrieval_metadata(self, state: AgentState) -> Dict[str, Any]:
        metadata = state.get("retrieval_metadata", {})
        if self.settings.debug_metadata:
            return metadata
        return {
            **compact_retrieval_metadata(metadata),
            "response_metadata": compact_response_metadata(
                state.get("response_metadata", {}),
                action=state["sales_plan"].macro_action,
                selected_action=state["sales_plan"].model_dump(),
                knowledge_plan=state["knowledge_plan"].model_dump(),
                token_usage=state.get("token_usage", {}),
            ),
        }

    def _stored_token_usage(self, state: AgentState) -> Dict[str, Any]:
        token_usage = state.get("token_usage", {})
        return token_usage if self.settings.debug_metadata else compact_token_usage(token_usage)


def should_use_deterministic_response(state: AgentState) -> bool:
    sales_plan = state.get("sales_plan")
    return bool(sales_plan and getattr(sales_plan, "next_question_key", None) == "entry_intent")


def merge_usage(existing: Dict[str, Any], usage: Dict[str, Any]) -> Dict[str, Any]:
    if not usage:
        return existing
    merged = {
        "calls": list(existing.get("calls", [])),
        "total": dict(
            existing.get(
                "total",
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            )
        ),
    }
    merged["calls"].append(usage)
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        merged["total"][key] = int(merged["total"].get(key) or 0) + int(usage.get(key) or 0)
    return merged


def attach_usage_details(usage: Dict[str, Any], key: str, value: Any) -> Dict[str, Any]:
    if not usage:
        return usage
    updated = dict(usage)
    details = dict(updated.get("details") or {})
    details[key] = value
    updated["details"] = details
    return updated


def _retrieved_sources_for_response(rag_context: Any) -> Any:
    sources = []
    for chunk in rag_context or []:
        content = str(chunk.get("content") or "")
        sources.append(
            {
                "title": chunk.get("title"),
                "source_path": chunk.get("source_path"),
                "similarity": chunk.get("similarity"),
                "metadata": chunk.get("metadata") or {},
                "preview": content[:360],
            }
        )
    return sources


def _lead_state_for_response(result: Dict[str, Any]) -> Dict[str, Any]:
    lead_state = dict(result.get("lead_profile") or {})
    action = result["sales_plan"].macro_action
    stage_transition = result.get("stage_transition")
    if stage_transition:
        lead_state.update(stage_transition.model_dump(exclude_none=True))
    else:
        lead_state["current_stage"] = result["sales_plan"].target_stage
    lead_state["last_action"] = action
    updates = result["analysis"].lead_updates.model_dump(exclude_none=True)
    for key in ("business_type", "main_channel", "pain", "urgency", "buying_signal"):
        if updates.get(key):
            lead_state[key] = updates[key]
    if updates.get("profile_data"):
        lead_state["profile_data"] = {
            **dict(lead_state.get("profile_data") or {}),
            **updates["profile_data"],
        }
    active_objection = result.get("active_objection")
    if active_objection:
        lead_state["active_objection"] = active_objection.model_dump()
    return lead_state


def _rag_metadata_filter(analysis: Any) -> Dict[str, Any]:
    return build_rag_route(analysis, None, "").metadata_filter


def _single_objection_playbook(playbook: Dict[str, Any], objection_type: str) -> Dict[str, Any]:
    objections = playbook.get("objections") or {}
    selected = objections.get(objection_type)
    if not selected:
        return {"objections": {}}
    return {
        "methodology": playbook.get("methodology") or [],
        "objections": {objection_type: selected},
    }
