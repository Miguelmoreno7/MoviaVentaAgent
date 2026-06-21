from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from openai import OpenAI

from movia_sales_agent.analyzer.contract_v3 import (
    ANALYZER_CONTRACT_VERSION,
    ANALYZER_V3_SCHEMA,
    AnalyzerTurnObservation,
    legacy_analysis_to_observation,
    observation_to_turn_analysis,
    validate_analyzer_observation,
)
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    BuyingSignal,
    Intent,
    ObjectionRelation,
    ObjectionStrength,
    ObjectionType,
    ProductFit,
    ReferenceType,
    Topic,
    enum_values,
)
from movia_sales_agent.models.schemas import TurnAnalysis


LEGACY_ANALYSIS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "primary_intent": {"type": "string", "enum": enum_values(Intent)},
        "secondary_intents": {
            "type": "array",
            "items": {"type": "string", "enum": enum_values(Intent)},
        },
        "topics": {"type": "array", "items": {"type": "string", "enum": enum_values(Topic)}},
        "skeptical_tone": {"type": "boolean"},
        "has_objection": {"type": "boolean"},
        "objection_type": {"type": "string", "enum": enum_values(ObjectionType)},
        "objection_strength": {"type": "string", "enum": enum_values(ObjectionStrength)},
        "objection_relation": {"type": "string", "enum": enum_values(ObjectionRelation)},
        "business_type": {"type": ["string", "null"]},
        "main_channel": {"type": ["string", "null"]},
        "pain": {"type": ["string", "null"]},
        "urgency": {"type": ["string", "null"]},
        "buying_signal": {"type": "string", "enum": enum_values(BuyingSignal)},
        "explicit_start_intent": {"type": "boolean"},
        "is_post_purchase": {"type": "boolean"},
        "references_prior_message": {"type": "boolean"},
        "reference_type": {"type": "string", "enum": enum_values(ReferenceType)},
        "reference_query": {"type": ["string", "null"]},
        "referenced_topics": {
            "type": "array",
            "items": {"type": "string", "enum": enum_values(Topic)},
        },
        "explicit_turn_number": {"type": ["integer", "null"], "minimum": 1},
        "reference_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "intent": {"type": "number", "minimum": 0, "maximum": 1},
                "objection": {"type": "number", "minimum": 0, "maximum": 1},
                "objection_relation": {"type": "number", "minimum": 0, "maximum": 1},
                "prior_reference": {"type": "number", "minimum": 0, "maximum": 1},
                "start_intent": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["intent", "objection", "objection_relation", "prior_reference", "start_intent"],
        },
        "lead_updates": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "business_type": {"type": ["string", "null"]},
                "main_channel": {"type": ["string", "null"]},
                "pain": {"type": ["string", "null"]},
                "urgency": {"type": ["string", "null"]},
                "buying_signal": {
                    "anyOf": [
                        {"type": "string", "enum": enum_values(BuyingSignal)},
                        {"type": "null"},
                    ]
                },
                "profile_data": {
                    "type": "object",
                    "properties": {
                        "action_requirement": {
                            "anyOf": [
                                {"type": "string", "enum": enum_values(ActionRequirement)},
                                {"type": "null"},
                            ],
                        },
                        "known_product_fit": {
                            "anyOf": [
                                {"type": "string", "enum": enum_values(ProductFit)},
                                {"type": "null"},
                            ],
                        },
                    },
                    "required": ["action_requirement", "known_product_fit"],
                    "additionalProperties": False,
                },
            },
            "required": [
                "business_type",
                "main_channel",
                "pain",
                "urgency",
                "buying_signal",
                "profile_data",
            ],
        },
    },
    "required": [
        "primary_intent",
        "secondary_intents",
        "topics",
        "skeptical_tone",
        "has_objection",
        "objection_type",
        "objection_strength",
        "objection_relation",
        "business_type",
        "main_channel",
        "pain",
        "urgency",
        "buying_signal",
        "explicit_start_intent",
        "is_post_purchase",
        "references_prior_message",
        "reference_type",
        "reference_query",
        "referenced_topics",
        "explicit_turn_number",
        "reference_confidence",
        "confidence",
        "lead_updates",
    ],
}

ANALYSIS_SCHEMA: Dict[str, Any] = ANALYZER_V3_SCHEMA


class OpenAIService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[OpenAI] = None
        if settings.openai_api_key and not settings.disable_openai:
            self.client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def analyze_turn(self, message: str, recent_messages: List[Dict[str, Any]]) -> TurnAnalysis:
        analysis, _usage = self.analyze_turn_with_usage(message, recent_messages)
        return analysis

    def analyze_turn_with_usage(
        self, message: str, recent_messages: List[Dict[str, Any]]
    ) -> Tuple[TurnAnalysis, Dict[str, Any]]:
        analysis, usage, _observation = self.analyze_turn_v3_with_usage(message, recent_messages)
        return analysis, usage

    def analyze_turn_v3_with_usage(
        self, message: str, recent_messages: List[Dict[str, Any]]
    ) -> Tuple[TurnAnalysis, Dict[str, Any], AnalyzerTurnObservation]:
        if not self.enabled:
            analysis = heuristic_analysis(message)
            observation = legacy_analysis_to_observation(analysis, message)
            usage = empty_usage("analysis", self.settings.analysis_model, "fallback")
            usage["details"] = {"analyzer_contract_version": ANALYZER_CONTRACT_VERSION}
            return analysis, usage, observation
        prompt = (
            "Analiza un mensaje de preventa de MovIA y devuelve solo JSON válido bajo Analyzer Contract V3.1. "
            "Tu tarea es observar lenguaje, no tomar decisiones comerciales. "
            "No recomiendes producto, no elijas etapa, no elijas acción comercial, no decidas CTA y no generes next_question. "
            "No devuelvas has_objection, references_prior_message, explicit_start_intent, explicit_turn_number, "
            "action_requirement, known_product_fit, recommended_product, sales_stage, macro_action, micro_action, cta_type ni needs_rag. "
            "Distingue entre lo que la persona le pregunta al vendedor de MovIA ahora y lo que quiere que haga el agente después de comprarlo. "
            "observed_business_problems captura dolores operativos actuales observables en el mensaje. "
            "requested_agent_capabilities solo captura capacidades futuras pedidas explícitamente para el agente comprado. "
            "requested_agent_actions solo captura acciones externas futuras pedidas explícitamente para ese agente, como agendar, cotizar, registrar, leer o escribir en sistemas. "
            "requirement_update_intent=no_change si el mensaje no cambia requisitos del agente futuro, merge si agrega requisitos nuevos, replace si redefine o limita explícitamente requisitos anteriores. "
            "No conviertas preguntas actuales de precio, proceso o venta al asesor en capacidades futuras del agente. "
            "requested_product solo identifica un producto mencionado por el usuario; nunca recomiendes uno. "
            "Una pregunta de precio no es una objeción; solo marca price_objection cuando haya resistencia a pagar. "
            "purchase_readiness.level=explicit_start solo si el usuario pide iniciar, contratar, pagar o recibir link. "
            "prior_reference.type no debe usar turnos numéricos; usa topic/entity/assistant commitment cuando haya evidencia. "
            "Cada evidence_span requerido debe ser una frase literal del mensaje actual."
        )
        try:
            response = self.client.responses.create(
                model=self.settings.analysis_model,
                input=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"message": message, "recent_messages": recent_messages[-6:]},
                            ensure_ascii=False,
                            default=json_default,
                        ),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "movia_analyzer_observation_v3",
                        "schema": ANALYZER_V3_SCHEMA,
                        "strict": True,
                    }
                },
            )
            usage = response_usage(response, "analysis", self.settings.analysis_model, "openai")
            observation = validate_analyzer_observation(json.loads(response.output_text), message)
            usage["details"] = {
                **dict(usage.get("details") or {}),
                "analyzer_contract_version": ANALYZER_CONTRACT_VERSION,
            }
            analysis = normalize_analysis(message, observation_to_turn_analysis(observation, message))
            return analysis, usage, observation
        except Exception as exc:
            usage = empty_usage("analysis", self.settings.analysis_model, "fallback")
            usage["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            analysis = heuristic_analysis(message)
            observation = legacy_analysis_to_observation(analysis, message)
            usage["details"] = {"analyzer_contract_version": ANALYZER_CONTRACT_VERSION}
            return analysis, usage, observation

    def generate_response(self, system_prompt: str, user_message: str, context: Dict[str, Any]) -> str:
        text, _usage = self.generate_response_with_usage(system_prompt, user_message, context)
        return text

    def generate_response_with_usage(
        self, system_prompt: str, user_message: str, context: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        if not self.enabled:
            return "", empty_usage("response", self.settings.response_model, "fallback")
        try:
            response = self.client.responses.create(
                model=self.settings.response_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"message": user_message, "context": context},
                            ensure_ascii=False,
                            default=json_default,
                        ),
                    },
                ],
            )
            usage = response_usage(response, "response", self.settings.response_model, "openai")
            return response.output_text.strip(), usage
        except Exception as exc:
            usage = empty_usage("response", self.settings.response_model, "fallback")
            usage["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            return "", usage

    def embed(self, texts: List[str]) -> List[List[float]]:
        embeddings, _usage = self.embed_with_usage(texts)
        return embeddings

    def embed_with_usage(self, texts: List[str]) -> Tuple[List[List[float]], Dict[str, Any]]:
        if not self.enabled:
            return [], empty_usage("embedding", self.settings.openai_embedding_model, "fallback")
        response = self.client.embeddings.create(
            model=self.settings.openai_embedding_model,
            input=texts,
            dimensions=self.settings.openai_embedding_dimensions,
        )
        usage = response_usage(response, "embedding", self.settings.openai_embedding_model, "openai")
        return [item.embedding for item in response.data], usage


def empty_usage(operation: str, model: str, provider: str) -> Dict[str, Any]:
    return {
        "operation": operation,
        "model": model,
        "provider": provider,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


def response_usage(response: Any, operation: str, model: str, provider: str) -> Dict[str, Any]:
    usage_obj = getattr(response, "usage", None)
    usage: Dict[str, Any] = empty_usage(operation, model, provider)
    if usage_obj is None:
        return usage
    for key in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens"):
        value = getattr(usage_obj, key, None)
        if isinstance(value, int):
            usage[key] = value
    if "prompt_tokens" in usage and not usage.get("input_tokens"):
        usage["input_tokens"] = usage["prompt_tokens"]
    if "completion_tokens" in usage and not usage.get("output_tokens"):
        usage["output_tokens"] = usage["completion_tokens"]
    if not usage.get("total_tokens"):
        usage["total_tokens"] = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
    details = {}
    for details_key in ("input_tokens_details", "output_tokens_details"):
        details_value = getattr(usage_obj, details_key, None)
        if details_value is not None:
            if hasattr(details_value, "model_dump"):
                details[details_key] = details_value.model_dump()
            else:
                details[details_key] = str(details_value)
    if details:
        usage["details"] = details
    return usage


def json_default(value: Any) -> str:
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def heuristic_analysis(message: str) -> TurnAnalysis:
    text = message.lower()
    topics: List[str] = []
    secondary_intents: List[str] = []
    future_agent_request = _has_future_agent_requirement_context(text)

    pain_description = _contains_any(
        text,
        [
            "desaparece",
            "desaparecen",
            "no responde",
            "no responden",
            "deja de contestar",
            "dejan de contestar",
            "nadie contesta",
            "nadie responde",
            "contesta rapido",
            "contesta rápido",
            "se enfria",
            "se enfría",
            "pierdo leads",
            "se pierden leads",
        ],
    )
    pricing_question = _contains_any(
        text, ["cuánto", "cuanto", "cuesta", "precio", "precios", "mensualidad", "deposito", "depósito"]
    )
    if pain_description and "pregunta precio" in text and not _contains_any(text, ["cuánto", "cuanto", "cuesta"]):
        pricing_question = False
    cheapest_plan_question = _contains_any(
        text, ["plan más barato", "plan mas barato", "plan más económico", "plan mas economico"]
    )
    platform_question = _contains_any(
        text,
        ["proceso", "registro", "página", "pagina", "llenar", "la app", "en app", "app.moviatech"],
    )
    demo_question = "demo" in text and _contains_any(
        text,
        ["probar", "prueba", "antes de pagar", "deposito", "depósito", "funciona", "crear"],
    )
    comparison_question = _contains_any(text, ["manychat", "chatbot", "recepcionista", "respuestas rápidas"])
    industry_fit_question = _contains_any(
        text, ["dental", "dentista", "clínica", "clinica", "restaurante", "inmobiliaria", "barberia", "barbería"]
    )
    channel_question = _contains_any(text, ["whatsapp", "facebook", "instagram"])
    product_scope_question = _contains_any(
        text,
        [
            "agendar",
            "agenda",
            "cotice",
            "cotizar",
            "cotización",
            "cotizacion",
            "ticket",
            "tickets",
            "foto",
            "fotos",
            "registrar",
            "proveedores",
            "recordatorio",
            "responder dudas",
            "responda dudas",
            "capturar datos",
            "capture datos",
            "suba a mi panel",
            "subir datos",
        ],
    )
    policy_question = _contains_any(
        text, ["reembolso", "mensualidad", "tokens", "deposito", "depósito", "pago final", "soporte"]
    )
    onboarding_question = _contains_any(text, ["documentos", "pdf", "ejemplos", "activar", "activación"])
    answers_only = future_agent_request and _contains_any(
        text,
        [
            "solo responder",
            "solamente responder",
            "responder dudas",
            "contestar dudas",
            "contestar preguntas",
            "responder preguntas",
            "capturar leads",
        ],
    )
    external_actions_required = future_agent_request and _contains_any(
        text,
        [
            "agendar",
            "agenda",
            "cotice",
            "cotizar",
            "cotización",
            "cotizacion",
            "ticket",
            "tickets",
            "foto",
            "fotos",
            "registrar",
            "proveedores",
            "recordatorio",
            "suba a mi panel",
            "subir datos",
            "datos de garantía",
            "datos de garantia",
        ],
    )
    unavailable_sales_requested = future_agent_request and _contains_any(
        text,
        [
            "cerrar ventas",
            "vender por mi",
            "venda por mi",
            "persuadir clientes",
            "convencer clientes",
            "seguimiento comercial",
        ],
    )
    unavailable_pro_requested = future_agent_request and _contains_any(
        text,
        [
            "pro comercial",
            "consultoría avanzada",
            "consultoria avanzada",
            "agente a la medida",
            "custom",
            "desarrollo personalizado",
        ],
    )

    if pricing_question:
        topics.append(Topic.PRICING.value)
    if product_scope_question:
        topics.append(Topic.PRODUCT_SCOPE.value)
    if platform_question or demo_question:
        topics.append(Topic.PLATFORM_PROCESS.value)
    if onboarding_question:
        topics.append(Topic.ONBOARDING.value)
    if comparison_question:
        topics.append(Topic.COMPETITOR_COMPARISON.value)
    if industry_fit_question:
        topics.extend([Topic.BUSINESS_FIT.value, Topic.INDUSTRY_USE_CASE.value])
    if "whatsapp" in text:
        topics.append(Topic.WHATSAPP.value)
    if "facebook" in text:
        topics.append(Topic.FACEBOOK.value)
    if "instagram" in text:
        topics.append(Topic.INSTAGRAM.value)
    if "integr" in text or "conectar" in text:
        topics.append(Topic.INTEGRATION.value)
    if "demo" in text:
        topics.append(Topic.DEMO.value)
    if "pdf" in text or "document" in text:
        topics.append(Topic.DOCUMENTS.value)
    if "ejemplo" in text:
        topics.append(Topic.CONVERSATION_EXAMPLES.value)
    if "reembolso" in text:
        topics.append(Topic.REFUND_POLICY.value)
    if "mensualidad" in text:
        topics.append(Topic.MONTHLY_PAYMENT.value)
    if "deposito" in text or "depósito" in text:
        topics.append(Topic.DEPOSIT.value)
    if "soporte" in text:
        topics.append(Topic.SUPPORT.value)
    if pain_description:
        topics.append(Topic.PRODUCT_RECOMMENDATION.value)
    if unavailable_sales_requested or unavailable_pro_requested:
        topics.append(Topic.PRODUCT_SCOPE.value)
    prior_reference = _prior_reference_fields(text, message, topics)
    for topic in prior_reference["referenced_topics"]:
        _append_unique(topics, topic)

    explicit_start_intent = _contains_any(
        text,
        [
            "quiero empezar",
            "quiero iniciar",
            "dónde pago",
            "donde pago",
            "quiero contratar",
            "contratar captura",
            "vamos a hacerlo",
            "cómo inicio",
            "como inicio",
            "pásame el link",
            "pasame el link",
            "mándame el link",
            "mandame el link",
            "manda el link",
            "dame el link",
        ],
    )
    is_post_purchase = any(
        phrase in text
        for phrase in ["ya pagué", "ya pague", "ya soy cliente", "ya contraté", "ya contrate"]
    )

    skeptical_tone = _contains_any(
        text, ["seguro es otro bot", "contesta tonter", "a ver convenceme", "no me digas que"]
    )
    objection_type = ObjectionType.NONE.value
    objection_strength = ObjectionStrength.SOFT.value if skeptical_tone else ObjectionStrength.NONE.value
    objection_relation = ObjectionRelation.NONE.value
    if _contains_any(text, ["prueba gratis", "sin deposito", "sin depósito"]) and _contains_any(
        text, ["si funciona pago", "gratis", "sin deposito", "sin depósito"]
    ):
        objection_type = ObjectionType.WANTS_FREE_TRIAL.value
        objection_strength = ObjectionStrength.HARD.value
        explicit_start_intent = False
    elif _contains_any(
        text,
        [
            "se me hace caro",
            "muy caro",
            "demasiado caro",
            "no pienso pagar",
            "se sale de mi presupuesto",
            "se fue caro",
        ],
    ):
        objection_type = ObjectionType.PRICE_OBJECTION.value
        objection_strength = ObjectionStrength.HARD.value
    elif "ya tengo" in text and _contains_any(text, ["persona", "recepcionista", "alguien"]):
        objection_type = ObjectionType.ALREADY_HAVE_PERSON.value
        objection_strength = ObjectionStrength.SOFT.value
    elif _contains_any(text, ["whatsapp business gratis", "respuestas rapidas", "respuestas rápidas"]):
        objection_type = ObjectionType.ALREADY_USE_WHATSAPP_BUSINESS.value
        objection_strength = ObjectionStrength.SOFT.value
    elif _contains_any(text, ["manychat es mejor", "prefiero manychat", "ya uso manychat"]):
        objection_type = ObjectionType.COMPETITOR_COMPARISON.value
        objection_strength = ObjectionStrength.SOFT.value
    elif _contains_any(text, ["responda mal", "conteste mal", "contesta mal", "perder control", "me quema"]):
        objection_type = ObjectionType.FEAR_WRONG_ANSWERS.value
        objection_strength = ObjectionStrength.HARD.value
    elif _contains_any(text, ["no confio", "no confío", "nadie responde", "va a fallar"]):
        objection_type = ObjectionType.TRUST_OBJECTION.value
        objection_strength = ObjectionStrength.HARD.value
    elif _contains_any(text, ["lo tengo que pensar", "necesito pensarlo"]):
        objection_type = ObjectionType.NEED_TO_THINK.value
        objection_strength = ObjectionStrength.SOFT.value
    elif _contains_any(text, ["no estoy seguro", "no sé si lo necesito", "no se si lo necesito"]):
        objection_type = ObjectionType.NOT_SURE_IF_NEEDED.value
        objection_strength = ObjectionStrength.SOFT.value
    elif _contains_any(text, ["conectar whatsapp", "conexion", "conexión"]):
        objection_type = ObjectionType.CHANNEL_CONNECTION_CONCERN.value
        objection_strength = ObjectionStrength.SOFT.value
    elif _contains_any(text, ["soporte", "whatsapp personal"]):
        objection_type = ObjectionType.SUPPORT_CONCERN.value
        objection_strength = ObjectionStrength.SOFT.value

    has_objection = objection_type != ObjectionType.NONE.value
    if has_objection:
        objection_relation = ObjectionRelation.NEW.value
    elif _contains_any(
        text,
        [
            "ok eso tiene sentido",
            "eso tiene sentido",
            "queda claro",
            "me queda claro",
            "ya entendi",
            "ya entendí",
            "me sirve",
            "suena bien",
            "me convenciste",
            "perfecto",
            "ya no es tanto problema",
            "no es tanto problema",
            "con eso ya no es tanto problema",
            "ya no me preocupa",
        ],
    ):
        objection_relation = ObjectionRelation.RESOLVED.value
    elif _contains_any(
        text,
        [
            "lo que me preocupa",
            "lo que me pesa",
            "mi duda es",
            "mi bloqueo",
            "pago inicial",
            "vale la pena",
            "recuperar tiempo",
            "ahorrar tiempo",
        ],
    ):
        objection_relation = ObjectionRelation.CLARIFIED.value
    elif _contains_any(text, ["demuestr", "muéstrame", "muestrame", "prueba", "evidencia", "caso real"]):
        objection_relation = ObjectionRelation.CONTINUATION.value
    elif pricing_question or platform_question or policy_question or product_scope_question or comparison_question:
        objection_relation = ObjectionRelation.UNRELATED.value

    buying_signal = BuyingSignal.NONE.value
    if explicit_start_intent:
        buying_signal = BuyingSignal.EXPLICIT_START.value
    elif _contains_any(text, ["me interesa", "me convenciste", "suena bien"]):
        buying_signal = BuyingSignal.MEDIUM.value
    elif pricing_question or product_scope_question:
        buying_signal = BuyingSignal.LOW.value

    business_type = None
    if any(word in text for word in ["dentista", "dental", "clínica", "clinica"]):
        business_type = "dental"
    elif "restaurante" in text:
        business_type = "restaurant"
    elif "inmobiliaria" in text or "bienes raíces" in text:
        business_type = "real_estate"

    main_channel = None
    if "whatsapp" in text:
        main_channel = "whatsapp"
    elif "facebook" in text:
        main_channel = "facebook"
    elif "instagram" in text:
        main_channel = "instagram"

    pain = None
    if pain_description:
        pain = "leads_disappear_after_price_question" if "precio" in text else "slow_or_missed_follow_up"

    profile_data: Dict[str, Any] = {}
    if answers_only and not external_actions_required:
        profile_data["action_requirement"] = ActionRequirement.ANSWERS_ONLY.value
        profile_data["known_product_fit"] = ProductFit.MOVIA_CAPTURA.value
    elif external_actions_required:
        profile_data["action_requirement"] = ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
        profile_data["known_product_fit"] = ProductFit.MOVIA_HIBRIDO.value
    elif pain_description:
        profile_data["action_requirement"] = ActionRequirement.UNKNOWN.value

    if unavailable_sales_requested:
        profile_data["known_product_fit"] = ProductFit.MOVIA_VENTAS_UNAVAILABLE.value
    elif unavailable_pro_requested:
        profile_data["known_product_fit"] = ProductFit.MOVIA_PRO_COMERCIAL_UNAVAILABLE.value

    primary_intent = Intent.GENERAL_INFO.value
    if is_post_purchase:
        primary_intent = Intent.POST_PURCHASE_REQUEST.value
        topics.append(Topic.POST_PURCHASE.value)
    elif explicit_start_intent:
        primary_intent = Intent.EXPLICIT_START_REQUEST.value
    elif cheapest_plan_question:
        primary_intent = Intent.CHEAPEST_PLAN_QUESTION.value
    elif pricing_question:
        primary_intent = Intent.PRICING_QUESTION.value
    elif product_scope_question:
        primary_intent = Intent.PRODUCT_SCOPE_QUESTION.value
    elif pain_description:
        primary_intent = Intent.PRODUCT_RECOMMENDATION_QUESTION.value
    elif platform_question or demo_question:
        primary_intent = Intent.PLATFORM_STEPS_QUESTION.value
    elif onboarding_question:
        primary_intent = Intent.ONBOARDING_QUESTION.value
    elif policy_question:
        primary_intent = Intent.POLICY_QUESTION.value
    elif comparison_question:
        primary_intent = Intent.COMPARISON_QUESTION.value
    elif channel_question:
        primary_intent = Intent.CHANNEL_QUESTION.value
    elif industry_fit_question:
        primary_intent = Intent.INDUSTRY_FIT_QUESTION.value
    elif _contains_any(text, ["hola", "buenas"]):
        primary_intent = Intent.GREETING.value
    elif not topics:
        primary_intent = Intent.UNKNOWN.value
        topics.append(Topic.UNKNOWN.value)

    for condition, intent in [
        (pricing_question and primary_intent != Intent.PRICING_QUESTION.value, Intent.PRICING_QUESTION.value),
        (
            industry_fit_question and primary_intent != Intent.INDUSTRY_FIT_QUESTION.value,
            Intent.INDUSTRY_FIT_QUESTION.value,
        ),
        (
            product_scope_question and primary_intent != Intent.PRODUCT_SCOPE_QUESTION.value,
            Intent.PRODUCT_SCOPE_QUESTION.value,
        ),
        (comparison_question and primary_intent != Intent.COMPARISON_QUESTION.value, Intent.COMPARISON_QUESTION.value),
        (policy_question and primary_intent != Intent.POLICY_QUESTION.value, Intent.POLICY_QUESTION.value),
    ]:
        if condition:
            secondary_intents.append(intent)

    return normalize_analysis(
        message,
        TurnAnalysis(
            primary_intent=primary_intent,
            secondary_intents=_dedupe(secondary_intents),
            topics=_dedupe(topics),
            skeptical_tone=skeptical_tone,
            has_objection=has_objection,
            objection_type=objection_type,
            objection_strength=objection_strength,
            objection_relation=objection_relation,
            business_type=business_type,
            main_channel=main_channel,
            pain=pain,
            buying_signal=buying_signal,
            explicit_start_intent=explicit_start_intent,
            is_post_purchase=is_post_purchase,
            references_prior_message=prior_reference["references_prior_message"],
            reference_type=prior_reference["reference_type"],
            reference_query=prior_reference["reference_query"],
            referenced_topics=prior_reference["referenced_topics"],
            explicit_turn_number=prior_reference["explicit_turn_number"],
            reference_confidence=prior_reference["reference_confidence"],
            confidence={
                "intent": 0.75,
                "objection": 0.8 if has_objection else 0.7,
                "objection_relation": 0.8 if objection_relation != ObjectionRelation.NONE.value else 0.6,
                "prior_reference": prior_reference["reference_confidence"],
                "start_intent": 0.95 if explicit_start_intent else 0.8,
            },
            lead_updates={
                "business_type": business_type,
                "main_channel": main_channel,
                "pain": pain,
                "urgency": None,
                "buying_signal": None if buying_signal == BuyingSignal.NONE.value else buying_signal,
                "profile_data": profile_data,
            },
        ),
    )


def normalize_analysis(message: str, analysis: TurnAnalysis) -> TurnAnalysis:
    text = message.lower()
    future_agent_request = _has_future_agent_requirement_context(text)
    pain_description = _contains_any(
        text,
        [
            "desaparece",
            "desaparecen",
            "no responde",
            "no responden",
            "deja de contestar",
            "dejan de contestar",
            "nadie contesta",
            "nadie responde",
            "contesta rapido",
            "contesta rápido",
            "pierdo leads",
            "se pierden leads",
        ],
    )
    if any(word in text for word in ["cuánto", "cuanto", "cuesta", "precio", "mensualidad", "deposito", "depósito"]):
        if not (pain_description and "pregunta precio" in text and not _contains_any(text, ["cuánto", "cuanto", "cuesta"])):
            _append_unique(analysis.topics, Topic.PRICING.value)
    if any(word in text for word in ["dental", "dentista", "clínica", "clinica"]):
        analysis.business_type = "dental"
        analysis.lead_updates.business_type = "dental"
        _append_unique(analysis.topics, Topic.BUSINESS_FIT.value)
        _append_unique(analysis.topics, Topic.INDUSTRY_USE_CASE.value)
    if "restaurante" in text:
        analysis.business_type = "restaurant"
        analysis.lead_updates.business_type = "restaurant"
        _append_unique(analysis.topics, Topic.BUSINESS_FIT.value)
        _append_unique(analysis.topics, Topic.INDUSTRY_USE_CASE.value)
    if "inmobiliaria" in text or "bienes raíces" in text:
        analysis.business_type = "real_estate"
        analysis.lead_updates.business_type = "real_estate"
        _append_unique(analysis.topics, Topic.BUSINESS_FIT.value)
        _append_unique(analysis.topics, Topic.INDUSTRY_USE_CASE.value)
    cheapest_plan_question = any(
        phrase in text
        for phrase in ["plan más barato", "plan mas barato", "plan más económico", "plan mas economico"]
    )
    if cheapest_plan_question:
        analysis.primary_intent = Intent.CHEAPEST_PLAN_QUESTION.value
        _append_unique(analysis.topics, Topic.PRICING.value)
        if analysis.objection_type == ObjectionType.PRICE_OBJECTION.value and not _contains_any(
            text, ["se me hace caro", "muy caro", "demasiado caro", "no pienso pagar", "se sale de mi presupuesto"]
        ):
            analysis.has_objection = False
            analysis.objection_type = ObjectionType.NONE.value
            analysis.objection_strength = ObjectionStrength.NONE.value
            analysis.objection_relation = ObjectionRelation.NONE.value
    if analysis.objection_type == ObjectionType.NONE.value:
        analysis.has_objection = False
        if not analysis.skeptical_tone:
            analysis.objection_strength = ObjectionStrength.NONE.value
        if analysis.objection_relation == ObjectionRelation.NEW.value:
            analysis.objection_relation = ObjectionRelation.NONE.value
    else:
        analysis.has_objection = True
        if analysis.objection_relation in {ObjectionRelation.NONE.value, ObjectionRelation.UNRELATED.value}:
            analysis.objection_relation = ObjectionRelation.NEW.value
    if analysis.explicit_start_intent:
        analysis.buying_signal = BuyingSignal.EXPLICIT_START.value
    if "whatsapp" in text and not analysis.main_channel:
        analysis.main_channel = "whatsapp"
        analysis.lead_updates.main_channel = "whatsapp"
    elif "facebook" in text and not analysis.main_channel:
        analysis.main_channel = "facebook"
        analysis.lead_updates.main_channel = "facebook"
    elif "instagram" in text and not analysis.main_channel:
        analysis.main_channel = "instagram"
        analysis.lead_updates.main_channel = "instagram"
    if pain_description:
        if analysis.primary_intent in {
            Intent.CHANNEL_QUESTION.value,
            Intent.PRICING_QUESTION.value,
            Intent.GENERAL_INFO.value,
            Intent.UNKNOWN.value,
        }:
            analysis.primary_intent = Intent.PRODUCT_RECOMMENDATION_QUESTION.value
        analysis.pain = analysis.pain or (
            "leads_disappear_after_price_question" if "precio" in text else "slow_or_missed_follow_up"
        )
        analysis.lead_updates.pain = analysis.lead_updates.pain or analysis.pain
        _append_unique(analysis.topics, Topic.PRODUCT_RECOMMENDATION.value)
    if future_agent_request and _contains_any(
        text,
        [
            "solo responder",
            "solamente responder",
            "responder dudas",
            "responda dudas",
            "contestar dudas",
            "contestar preguntas",
            "capturar datos",
            "capture datos",
            "responda precios",
            "responder precios",
            "de precios",
            "dé precios",
            "dar precios",
        ],
    ):
        analysis.lead_updates.profile_data.setdefault("action_requirement", ActionRequirement.ANSWERS_ONLY.value)
        analysis.lead_updates.profile_data.setdefault("known_product_fit", ProductFit.MOVIA_CAPTURA.value)
    if future_agent_request and _contains_any(
        text,
        [
            "agendar",
            "agenda",
            "cotice",
            "cotizar",
            "ticket",
            "tickets",
            "foto",
            "fotos",
            "registrar",
            "proveedores",
            "recordatorio",
            "datos de garantía",
            "datos de garantia",
        ],
    ):
        analysis.lead_updates.profile_data["action_requirement"] = ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
        analysis.lead_updates.profile_data.setdefault("known_product_fit", ProductFit.MOVIA_HIBRIDO.value)
    if future_agent_request and _contains_any(text, ["cerrar ventas", "vender por mi", "venda por mi", "persuadir clientes"]):
        analysis.lead_updates.profile_data["known_product_fit"] = ProductFit.MOVIA_VENTAS_UNAVAILABLE.value
    if future_agent_request and _contains_any(
        text,
        ["pro comercial", "consultoría avanzada", "consultoria avanzada", "agente a la medida", "custom"],
    ):
        analysis.lead_updates.profile_data["known_product_fit"] = ProductFit.MOVIA_PRO_COMERCIAL_UNAVAILABLE.value
    return analysis


def _prior_reference_fields(text: str, message: str, topics: List[str]) -> Dict[str, Any]:
    explicit_turn_number = _explicit_turn_number(text)
    references_prior = explicit_turn_number is not None or _contains_any(
        text,
        [
            "como te dije",
            "como dije",
            "te dije al inicio",
            "al inicio",
            "hace rato",
            "antes dijiste",
            "tu dijiste",
            "tú dijiste",
            "me dijiste",
            "me recomendaste",
            "plan que me recomendaste",
            "cuál era el plan",
            "cual era el plan",
            "lo de mis proveedores",
            "lo de proveedores",
            "lo de los proveedores",
            "eso que dijiste",
            "era captura o híbrido",
            "era captura o hibrido",
        ],
    )
    referenced_topics = []
    if _contains_any(text, ["plan", "recomendaste", "captura", "híbrido", "hibrido"]):
        referenced_topics.append(Topic.PRODUCT_RECOMMENDATION.value)
    if _contains_any(text, ["proveedor", "ticket", "foto", "garantía", "garantia"]):
        referenced_topics.append(Topic.PRODUCT_SCOPE.value)
    if _contains_any(text, ["deposito", "depósito", "50%"]):
        referenced_topics.extend([Topic.DEPOSIT.value, Topic.PLATFORM_PROCESS.value])
    if _contains_any(text, ["precio", "cuesta", "costaba"]):
        referenced_topics.append(Topic.PRICING.value)

    if explicit_turn_number is not None:
        reference_type = ReferenceType.EXPLICIT_TURN.value
    elif _contains_any(text, ["me recomendaste", "me dijiste", "tu dijiste", "tú dijiste", "antes dijiste"]):
        reference_type = ReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value
    elif _contains_any(text, ["al inicio", "hace rato", "antes"]):
        reference_type = ReferenceType.TEMPORAL_REFERENCE.value
    elif _contains_any(text, ["proveedor", "ticket", "foto", "plan", "deposito", "depósito"]):
        reference_type = ReferenceType.TOPIC_REFERENCE.value
    elif references_prior:
        reference_type = ReferenceType.ENTITY_REFERENCE.value
    else:
        reference_type = ReferenceType.NONE.value

    return {
        "references_prior_message": references_prior,
        "reference_type": reference_type,
        "reference_query": message if references_prior else None,
        "referenced_topics": _dedupe(referenced_topics or topics if references_prior else []),
        "explicit_turn_number": explicit_turn_number,
        "reference_confidence": 0.85 if references_prior else 0.0,
    }


def _explicit_turn_number(text: str) -> Optional[int]:
    import re

    match = re.search(r"(?:turno|mensaje|respuesta)\s+(\d+)", text)
    return int(match.group(1)) if match else None


def _contains_any(text: str, needles: List[str]) -> bool:
    return any(needle in text for needle in needles)


def _has_future_agent_requirement_context(text: str) -> bool:
    product_context_terms = [
        "movia captura",
        "movia hibrido",
        "movia híbrido",
        "captura",
        "hibrido",
        "híbrido",
    ]
    if _contains_any(text, product_context_terms) and _contains_any(text, [" para ", " puede ", " podría ", " podria "]):
        return True
    return _contains_any(
        text,
        [
            "quiero que",
            "necesito que",
            "busco que",
            "que el agente",
            "mi agente",
            "quiero movia",
            "quiero captura",
            "quiero hibrido",
            "quiero híbrido",
            "lo quiero para",
            "necesito un agente",
            "solo que",
            "solamente que",
            "entonces solo",
            "mejor solo",
            "por ahora solo",
        ],
    )


def _append_unique(values: List[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _dedupe(values: List[str]) -> List[str]:
    result = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
