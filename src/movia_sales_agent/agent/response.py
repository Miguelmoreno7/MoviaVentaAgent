from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from movia_sales_agent.agent.memory import fallback_reference_response
from movia_sales_agent.agent.fulfillment import (
    NEXT_QUESTION_REPLACE_MINIMAL,
    NEXT_QUESTION_SUPPRESS,
    minimal_question_for,
)
from movia_sales_agent.agent.requirements import (
    build_requirement_summary,
    ensure_requirement_profile,
)
from movia_sales_agent.contracts.commercial import CTAType, Intent, MacroAction, MicroAction, ObjectionType, Topic
from movia_sales_agent.ingestion.chunker import estimate_tokens
from movia_sales_agent.models.schemas import SalesPlan, TurnAnalysis


BASE_SYSTEM_PROMPT = """
Eres el agente de preventa de MovIA.
Tu objetivo es informar, recomendar y avanzar una micro-etapa comercial.
Responde solo con información oficial recibida en contexto.
No inventes precios, tiempos, links, features, canales ni políticas.
Actualmente WhatsApp Business está disponible; Facebook e Instagram están en proceso.
MovIA Captura y MovIA Híbrido están disponibles.
En respuestas públicas enfócate en MovIA Captura y MovIA Híbrido.
No resuelvas soporte post-compra complejo; redirige a Miguel.
Habla claro, cercano, consultivo y breve.
Redacta para WhatsApp: párrafos cortos, listas fáciles de escanear y una sola idea por bloque.
Evita bloques largos de texto; si hay varios pasos, separa la respuesta con saltos de línea.
""".strip()


def build_generation_context(
    analysis: TurnAnalysis,
    sales_plan: SalesPlan,
    structured_context: Dict[str, Any],
    json_context: Dict[str, Any],
    rag_context: List[Dict[str, Any]],
    recent_messages: List[Dict[str, Any]],
    lead_profile: Optional[Dict[str, Any]] = None,
    stage_transition: Optional[Any] = None,
    active_objection: Optional[Any] = None,
    structured_memory: Optional[Dict[str, Any]] = None,
    conversation_memory_evidence: Optional[List[Dict[str, Any]]] = None,
    normalized_turn: Optional[Dict[str, Any]] = None,
    response_fulfillment_policy: Optional[Dict[str, Any]] = None,
    purchase_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    lead_context = _compact_lead_context(
        analysis,
        lead_profile or {},
        stage_transition=stage_transition,
        active_objection=active_objection,
    )
    official_facts = _compact_official_facts(structured_context)
    turn_signal_context = _compact_turn_signal_context(normalized_turn or {})
    claim_constraints = _claim_constraints(normalized_turn or {})
    fulfillment_policy = response_fulfillment_policy or {}
    purchase_status = purchase_status or {}
    playbook_instruction = _apply_fulfillment_policy_to_playbook(
        _compact_playbook_instruction(analysis, sales_plan, json_context),
        fulfillment_policy,
    )
    context = {
        "commercial_instruction": _commercial_instruction(sales_plan, stage_transition),
        "lead_context": lead_context,
        "official_facts": official_facts,
        "playbook_instruction": playbook_instruction,
        "turn_signal_context": turn_signal_context,
        "response_fulfillment_policy": fulfillment_policy,
        "memory_context": _compact_memory_context(
            structured_memory or {},
            conversation_memory_evidence or [],
        ),
        "rag_context": _compact_rag_context(rag_context),
        "recent_messages": _select_recent_messages(recent_messages, analysis, lead_context),
        "claim_constraints": claim_constraints,
        "response_requirements": _response_requirements(
            sales_plan=sales_plan,
            official_facts=official_facts,
            normalized_turn=normalized_turn or {},
            response_fulfillment_policy=fulfillment_policy,
            purchase_status=purchase_status,
        ),
    }
    if purchase_status:
        context["purchase_status"] = purchase_status
    return context


def _response_requirements(
    *,
    sales_plan: SalesPlan,
    official_facts: Dict[str, Any],
    normalized_turn: Dict[str, Any],
    response_fulfillment_policy: Dict[str, Any],
    purchase_status: Dict[str, Any],
) -> List[str]:
    requirements = [
            "Contestar la duda explícita.",
            "Usar solo datos del contexto.",
            "Redactar para WhatsApp con bloques breves.",
            "Cerrar con una sola pregunta o CTA salvo handoff.",
            "Si existe objection_overlay, responder primero la intención actual y aplicar la restricción de cierre indicada.",
            "No digas que Facebook o Instagram están disponibles hoy; solo WhatsApp Business está disponible actualmente.",
            "No describas ningún producto MovIA como multicanal actualmente.",
            "Si hablas de Captura, aclara que puede recopilar información en WhatsApp pero no registrar pedidos en sistemas externos.",
            "No mencionar arquitectura interna.",
    ]
    requirements.extend(_official_product_response_requirements(official_facts, normalized_turn))
    requirements.extend(_payment_response_requirements(sales_plan, official_facts))
    requirements.extend(_post_purchase_gate_response_requirements(sales_plan, purchase_status))
    requirements.extend(_requirement_profile_response_requirements(normalized_turn))
    requirements.extend(_fulfillment_response_requirements(response_fulfillment_policy))
    return requirements


def fallback_response(message: str, analysis: TurnAnalysis, sales_plan: SalesPlan, context: Dict[str, Any]) -> str:
    json_context = context.get("json_context", {})
    playbook_context = context.get("playbook_instruction") or {}
    products = _products_from_context(context)
    reference = fallback_reference_response(
        analysis,
        context.get("conversation_memory_evidence") or (context.get("memory_context") or {}).get("conversation_memory_evidence") or [],
    )
    if reference:
        return reference
    fulfillment = context.get("response_fulfillment_policy") or {}
    if "official_app_link" in set(fulfillment.get("mandatory_fulfillments") or []):
        app_link = ((context.get("official_facts") or {}).get("official_links") or {}).get("app")
        question = minimal_question_for(fulfillment)
        parts = [f"Claro, aquí está el link oficial: {app_link or 'https://app.moviatech.com.mx'}."]
        if question and fulfillment.get("next_question_policy") == NEXT_QUESTION_REPLACE_MINIMAL:
            parts.append(question)
        return "\n\n".join(parts)

    if sales_plan.macro_action == MacroAction.HANDOFF_TO_MIGUEL.value:
        if (
            sales_plan.micro_action == MicroAction.REDIRECT_CUSTOM_SCOPE.value
            or sales_plan.reason_code == "CUSTOM_SCOPE_REVIEW"
        ):
            return (
                "Eso suena más cercano a MovIA Híbrido, porque ya implica cotizar, registrar o escribir información en un sistema. "
                "Sí puede evaluarse, pero no te prometería compatibilidad con esa herramienta sin revisar el proceso y los accesos. "
                "¿Qué sistema usas y qué dato tendría que crear o actualizar el agente?"
            )
        handoff = json_context.get("post_purchase_handoff") or {}
        if not handoff:
            handoff = playbook_context.get("post_purchase_handoff") or {}
        return handoff.get(
            "message",
            "Si ya realizaste el depósito o ya eres cliente, Miguel te dará seguimiento personalizado por WhatsApp para revisar tu caso.",
        )

    if (
        sales_plan.macro_action == MacroAction.EXPLAIN_PROCESS.value
        and sales_plan.micro_action == MicroAction.EXPLAIN_HUMAN_HANDOFF.value
    ):
        return (
            "Una vez que el depósito quede confirmado en la plataforma, tendrás acceso al seguimiento personalizado. "
            "Mientras tanto, puedo ayudarte por aquí con cualquier duda del proceso."
        )

    if sales_plan.macro_action == MacroAction.DIRECT_CLOSE.value:
        cta = json_context.get("cta_rules") or {}
        if not cta:
            cta = {"direct_close": (playbook_context.get("cta") or {}).get("text")}
        return cta.get("direct_close") or (
            "Puedes iniciar desde app.moviatech.com.mx. Ahí eliges tu agente, llenas la información inicial y pagas el 50% de depósito para que podamos comenzar."
        )

    if sales_plan.macro_action == MacroAction.HANDLE_OBJECTION.value:
        objection = _objection_response(
            analysis,
            sales_plan,
            {**json_context, "playbook_instruction": playbook_context},
        )
        if objection:
            return objection

    if sales_plan.macro_action == MacroAction.ANSWER_UNKNOWN_SAFELY.value:
        return (
            "Para no inventarte algo fuera del alcance de MovIA, necesito aterrizarlo a tu flujo. "
            "MovIA ayuda principalmente a responder, capturar datos y, en Híbrido, apoyar con acciones operativas acordadas. "
            "¿Qué parte de tu atención quieres automatizar primero?"
        )

    if (
        analysis.primary_intent == Intent.GREETING.value
        and sales_plan.micro_action == MicroAction.ANSWER_GENERAL_THEN_DISCOVER_NEED.value
    ):
        return (
            "¡Hola! Soy el asistente de MovIA.\n\n"
            "Te puedo ayudar a ver si un agente para WhatsApp tiene sentido para tu negocio.\n\n"
            "¿Vienes buscando información general o quieres cotizar algo específico?"
        )

    if Topic.PLATFORM_PROCESS.value in analysis.topics or sales_plan.macro_action == MacroAction.EXPLAIN_PROCESS.value:
        if Topic.DEMO.value in analysis.topics or "demo" in message.lower():
            return (
                "Sí, puedes probar un demo dentro de la app de MovIA antes de pagar. "
                "El demo está limitado a 10 mensajes y sirve para entender cómo funciona el agente y cómo cambian sus respuestas con instrucciones. "
                "No requiere depósito, no inicia trabajo personalizado y no se despliega en tu WhatsApp. "
                "El depósito del 50% aplica solo si decides crear un agente personalizado."
            )
        steps = (
            (json_context.get("platform_steps") or {}).get("steps")
            or (playbook_context.get("process") or {}).get("steps")
            or []
        )
        short_steps = " ".join(f"{index + 1}. {step}" for index, step in enumerate(steps[:5]))
        return (
            f"Para empezar: {short_steps} Si eliges proyecto personalizado, después revisas tu pedido y pagas el 50% de depósito por Stripe. "
            "El link oficial es https://app.moviatech.com.mx. ¿Quieres que te recomiende primero entre Captura e Híbrido?"
        )

    if sales_plan.micro_action == MicroAction.ANSWER_CHANNEL_THEN_DISCOVER_MAIN_CHANNEL.value:
        next_question = sales_plan.next_question or "¿Qué tipo de negocio tienes?"
        return (
            "Hoy el canal disponible para MovIA es WhatsApp Business. "
            "Facebook e Instagram están en proceso, así que no te los presentaría como canales activos todavía. "
            f"{next_question}"
        )

    if sales_plan.macro_action == MacroAction.NARROW_SOLUTION.value:
        return _narrow_solution_response(analysis, sales_plan)

    if sales_plan.macro_action == MacroAction.RISK_REVERSAL.value:
        return (
            "Sí hay una parte de control antes de activar: MovIA se configura con tu información, se revisa contigo "
            "y se ajusta antes de dejarlo listo. El depósito inicia el proyecto y no se maneja como prueba gratis, "
            "pero el demo sirve para validar el estilo de respuesta antes de comprar. ¿Qué riesgo te preocupa más?"
        )

    if Topic.PRICING.value in analysis.topics:
        return _pricing_response(products, context.get("rag_context", []), analysis)

    if Topic.COMPETITOR_COMPARISON.value in analysis.topics or sales_plan.macro_action == MacroAction.COMPARE_ALTERNATIVE.value:
        return (
            "MovIA no está pensado como una herramienta DIY de flujos; está pensado como una solución configurada para tu negocio. "
            "Tú das tu información, ejemplos y objetivo, y MovIA construye el agente para responder con contexto en WhatsApp Business. "
            "Para orientarte mejor, ¿buscas solo responder preguntas o también necesitas que el agente haga acciones como agendar o registrar datos?"
        )

    if sales_plan.macro_action == MacroAction.PERSUADE_VALUE.value:
        return (
            "La diferencia práctica es que MovIA no solo contesta por contestar: usa la información de tu negocio para responder rápido, "
            "filtrar interesados y mantener una experiencia más consistente cuando tú o tu equipo no alcanzan a responder. "
            "Para recomendarte bien, ¿qué tipo de negocio tienes?"
        )

    if sales_plan.micro_action == MicroAction.EXPLAIN_VENTAS_NOT_AVAILABLE.value:
        return (
            "Hoy podemos revisar si MovIA Captura o MovIA Híbrido cubren tu necesidad actual: responder, capturar datos o hacer acciones operativas acordadas. "
            "¿Qué necesitas que haga el agente después de responder?"
        )

    if sales_plan.micro_action == MicroAction.EXPLAIN_PRO_COMERCIAL_NOT_AVAILABLE.value:
        return (
            "Si tu alcance es muy personalizado, conviene revisarlo aparte con Miguel. "
            "Si tu necesidad es responder, capturar datos o hacer acciones operativas acordadas, puedo orientarte entre MovIA Captura y MovIA Híbrido. "
            "¿Qué proceso quieres automatizar?"
        )

    if sales_plan.macro_action == MacroAction.SOFT_CLOSE.value:
        return (
            "Por lo que me cuentas, sí suena viable avanzar con MovIA. "
            "Antes de mandarte el link, ¿quieres que te confirme si te conviene más Captura o Híbrido?"
        )

    if sales_plan.macro_action == MacroAction.DISCOVER_NEED.value:
        return sales_plan.next_question or (
            "¿Qué parte de tu atención quieres automatizar primero?"
        )

    if sales_plan.macro_action == MacroAction.RECOMMEND_SOLUTION.value:
        recommendation = recommend_product(message, products, sales_plan=sales_plan)
        if recommendation:
            return recommendation

    cta = json_context.get("cta_rules") or {}
    if not cta:
        cta = {"discovery_question": (playbook_context.get("cta") or {}).get("text")}
    return cta.get("discovery_question") or (
        "Para orientarte mejor, ¿qué tipo de negocio tienes y por dónde te escriben más tus clientes?"
    )


def _apply_fulfillment_policy_to_playbook(
    playbook: Dict[str, Any],
    response_fulfillment_policy: Dict[str, Any],
) -> Dict[str, Any]:
    policy = str(response_fulfillment_policy.get("next_question_policy") or "")
    if policy not in {NEXT_QUESTION_REPLACE_MINIMAL, NEXT_QUESTION_SUPPRESS}:
        return playbook
    result = dict(playbook)
    micro_action = dict(result.get("micro_action") or {})
    cta = dict(result.get("cta") or {})
    if policy == NEXT_QUESTION_SUPPRESS:
        micro_action["next_question"] = None
        micro_action["next_question_key"] = None
    else:
        question = minimal_question_for(response_fulfillment_policy)
        micro_action["next_question"] = question
        micro_action["next_question_key"] = response_fulfillment_policy.get("minimal_question_key")
        if question:
            cta["text"] = question
    result["micro_action"] = _drop_empty(micro_action)
    result["cta"] = _drop_empty(cta)
    return result


def _pricing_response(
    products: List[Dict[str, Any]], rag_context: List[Dict[str, Any]], analysis: TurnAnalysis
) -> str:
    available = [product for product in products if product.get("status") == "available"]
    future = [product for product in products if product.get("status") != "available"]
    if not available:
        return (
            "Necesito consultar los precios oficiales antes de responderte para no inventar. "
            "¿Me cuentas qué tipo de agente necesitas: responder dudas o también hacer acciones?"
        )
    lines = []
    for product in available:
        lines.append(
            f"{product['name']}: setup ${int(product['setup_price_mxn']):,} MXN y mensualidad ${int(product['monthly_price_mxn']):,} MXN."
        )
    future_names = ", ".join(product["name"] for product in future)
    suffix = f" {future_names} aparecen como no disponibles por ahora." if future_names else ""
    industry_note = _industry_note(rag_context, analysis)
    if industry_note:
        cheapest = min(available, key=lambda product: product.get("setup_price_mxn") or 99999999)
        return (
            f"El plan más barato disponible es {cheapest['name']}: setup ${int(cheapest['setup_price_mxn']):,} MXN "
            f"y mensualidad ${int(cheapest['monthly_price_mxn']):,} MXN. {industry_note} "
            "Si además quieres que el agente agende citas o mande recordatorios, ahí convendría MovIA Híbrido."
        )
    return (
        "Los planes disponibles son: "
        + " ".join(lines).replace(",", ",")
        + suffix
        + " Si solo necesitas responder y capturar leads, normalmente Captura es suficiente; si necesitas agendar, cotizar o registrar datos, conviene Híbrido."
    )


def _industry_note(rag_context: List[Dict[str, Any]], analysis: TurnAnalysis) -> str:
    industry = analysis.business_type or analysis.lead_updates.business_type
    dental_context = any((chunk.get("metadata") or {}).get("industry") == "dental" for chunk in rag_context)
    if industry == "dental" or dental_context:
        return (
            "Para una clínica dental conviene porque suelen llegar preguntas repetidas sobre tratamientos, precios, horarios, ubicación y disponibilidad; "
            "MovIA Captura ayuda a responder rápido y capturar datos básicos del paciente como nombre, tratamiento de interés y horario preferido."
        )
    return ""


def _objection_response(
    analysis: TurnAnalysis, sales_plan: SalesPlan, json_context: Dict[str, Any]
) -> Optional[str]:
    playbook = (json_context.get("objection_playbook") or {}).get("objections") or {}
    if not playbook and json_context.get("playbook_instruction"):
        objection = json_context["playbook_instruction"].get("objection") or {}
        if objection.get("type"):
            playbook = {objection["type"]: objection}
    objection_type = analysis.objection_type or ""
    if not objection_type or objection_type == ObjectionType.NONE.value:
        objection_type = next(iter(playbook.keys()), "")
    objection = playbook.get(objection_type)
    if not objection:
        return None
    question = objection.get("first_question")
    if sales_plan.objection_flow_step == "clarify_value":
        return (
            "Va, quiero entender bien el bloqueo antes de darte una respuesta genérica. "
            f"{question or '¿Qué parte te preocupa más: costo, confianza, alcance o timing?'}"
        )
    if sales_plan.objection_flow_step == "tie_solution":
        return (
            "Con eso en mente, lo importante es conectar MovIA al problema real: responder mejor, filtrar mejor "
            "y evitar que el seguimiento dependa solo de una persona. ¿Ese es el punto que más quieres resolver?"
        )
    if sales_plan.objection_flow_step == "provide_proof":
        return (
            "La parte segura es esta: MovIA se configura con tu información, se revisa contigo y se ajusta antes de activarlo. "
            "No te prometería resultados inventados; sí puedo explicarte el proceso de revisión, demo y límites del producto."
        )
    if sales_plan.objection_flow_step == "close_or_continue":
        return (
            "Entonces lo cerraría así: si esa preocupación queda cubierta, podemos seguir con la recomendación; "
            "si todavía hay una duda, la aterrizamos antes de avanzar. ¿Quieres que retomemos qué producto te conviene?"
        )
    if sales_plan.objection_flow_step == "resolved":
        return (
            "Perfecto, entonces dejamos esa preocupación cubierta y retomamos el siguiente paso comercial sin reiniciar. "
            "¿Quieres que retomemos qué producto te conviene?"
        )
    if objection_type == ObjectionType.PRICE_OBJECTION.value:
        return (
            "Te entiendo, y gracias por decirlo directo. "
            f"{question}"
        )
    return question


def _narrow_solution_response(analysis: TurnAnalysis, sales_plan: SalesPlan) -> str:
    profile_data = dict(analysis.lead_updates.profile_data or {})
    action_requirement = profile_data.get("action_requirement")
    if (
        action_requirement == "external_actions_required"
        or sales_plan.micro_action
        in {
            MicroAction.DETERMINE_IF_EXTERNAL_ACTIONS_ARE_NEEDED.value,
            MicroAction.DIFFERENTIATE_CAPTURA_VS_HIBRIDO.value,
        }
    ):
        return (
            "Para ese flujo conviene separar dos cosas: Captura puede recopilar información dentro de WhatsApp, "
            "pero no registra pedidos ni escribe datos en sistemas externos. "
            "Si necesitas cotizar, agendar, registrar información o interactuar con una herramienta aprobada, el camino correcto es MovIA Híbrido con revisión de alcance. "
            f"{sales_plan.next_question or '¿Qué acción externa necesitas que haga primero?'}"
        )
    return (
        "Antes de recomendarte Captura o Híbrido necesito aclarar el alcance. "
        f"{sales_plan.next_question or '¿El agente solo debe responder/capturar datos o también hacer acciones como agendar, cotizar o registrar información?'}"
    )


def recommend_product(
    message: str,
    products: List[Dict[str, Any]],
    *,
    sales_plan: Optional[SalesPlan] = None,
) -> str:
    text = message.lower()
    needs_action = any(
        word in text
        for word in [
            "agendar",
            "agenda",
            "cotizar",
            "cotización",
            "cotizacion",
            "ticket",
            "tickets",
            "fotos",
            "registrar",
            "proveedores",
            "recordatorio",
        ]
    )
    if sales_plan and sales_plan.micro_action == MicroAction.RECOMMEND_MOVIA_HIBRIDO.value:
        needs_action = True
    if sales_plan and sales_plan.micro_action == MicroAction.RECOMMEND_MOVIA_CAPTURA.value:
        needs_action = False
    product_slug = "movia-hibrido" if needs_action else "movia-captura"
    product = next((item for item in products if item.get("slug") == product_slug), None)
    if not product:
        return ""
    reason = (
        "porque necesitas que el agente haga una acción además de responder"
        if needs_action
        else "porque tu necesidad principal parece ser responder dudas, capturar leads y filtrar interesados"
    )
    external_system_scope = needs_action and any(
        word in text
        for word in [
            "sistema",
            "crm",
            "erp",
            "contable",
            "api",
            "panel",
            "herramienta",
            "plataforma",
        ]
    )
    caveat = (
        " Si implica escribir, consultar o actualizar una herramienta específica, se puede evaluar dentro de Híbrido, pero no se garantiza compatibilidad sin revisión técnica del proceso y accesos."
        if external_system_scope
        else ""
    )
    return (
        f"Por lo que me cuentas, te conviene más {product['name']} {reason}. "
        f"Su setup es de ${int(product['setup_price_mxn']):,} MXN y la mensualidad es de ${int(product['monthly_price_mxn']):,} MXN."
        f"{caveat} "
        "¿Tu flujo necesita alguna acción específica como agendar, cotizar o registrar datos?"
    )


def response_package_token_estimates(
    context: Dict[str, Any],
    system_prompt: str = BASE_SYSTEM_PROMPT,
    user_message: str = "",
) -> Dict[str, int]:
    sections = {
        "system_prompt": estimate_tokens(system_prompt),
        "commercial_instruction": _estimate_section(context.get("commercial_instruction")),
        "lead_context": _estimate_section(context.get("lead_context")),
        "official_facts": _estimate_section(context.get("official_facts")),
        "playbook": _estimate_section(context.get("playbook_instruction")),
        "turn_signal_context": _estimate_section(context.get("turn_signal_context")),
        "response_fulfillment_policy": _estimate_section(context.get("response_fulfillment_policy")),
        "memory_context": _estimate_section(context.get("memory_context")),
        "rag_context": _estimate_section(context.get("rag_context")),
        "recent_messages": _estimate_section(context.get("recent_messages")),
        "claim_constraints": _estimate_section(context.get("claim_constraints")),
        "response_requirements": _estimate_section(context.get("response_requirements")),
        "user_message": estimate_tokens(user_message or ""),
    }
    sections["context_total_estimate"] = _estimate_section(context)
    sections["response_input_total_estimate"] = sections["system_prompt"] + estimate_tokens(
        json.dumps(
            {"message": user_message, "context": context},
            ensure_ascii=False,
            default=str,
        )
    )
    return sections


def _estimate_section(value: Any) -> int:
    return estimate_tokens(json.dumps(value, ensure_ascii=False, default=str))


def _commercial_instruction(sales_plan: SalesPlan, stage_transition: Optional[Any]) -> Dict[str, Any]:
    return {
        "stage": _field(stage_transition, "current_stage") or sales_plan.target_stage,
        "conversation_mode": _field(stage_transition, "conversation_mode"),
        "target_stage": sales_plan.target_stage,
        "macro_action": sales_plan.macro_action,
        "micro_action": sales_plan.micro_action,
        "goal": sales_plan.commercial_goal,
        "cta_type": sales_plan.cta_type,
        "objection_flow_step": sales_plan.objection_flow_step,
        "reason_code": sales_plan.reason_code,
        "next_question": sales_plan.next_question,
        "next_question_key": sales_plan.next_question_key,
        "objection_overlay": _as_dict(sales_plan.objection_overlay),
    }


def _compact_lead_context(
    analysis: TurnAnalysis,
    lead_profile: Dict[str, Any],
    *,
    stage_transition: Optional[Any],
    active_objection: Optional[Any],
) -> Dict[str, Any]:
    lead_profile_data = dict(lead_profile.get("profile_data") or {})
    analysis_profile_data = dict(analysis.lead_updates.profile_data or {})
    profile_data = {**lead_profile_data, **analysis_profile_data}
    requirement_profile = ensure_requirement_profile(profile_data)
    requirement_summary = build_requirement_summary(
        requirement_profile,
        requested_product=profile_data.get("requested_product"),
    )
    result = _drop_empty(
        {
            "business_type": analysis.business_type
            or analysis.lead_updates.business_type
            or lead_profile.get("business_type"),
            "main_channel": analysis.main_channel
            or analysis.lead_updates.main_channel
            or lead_profile.get("main_channel"),
            "pain": analysis.pain or analysis.lead_updates.pain or lead_profile.get("pain"),
            "urgency": analysis.urgency
            or analysis.lead_updates.urgency
            or lead_profile.get("urgency"),
            "buying_signal": analysis.buying_signal or lead_profile.get("buying_signal"),
            "action_requirement": profile_data.get("action_requirement"),
            "known_product_fit": profile_data.get("known_product_fit"),
            "requirement_class": requirement_summary.get("requirement_class"),
            "requirement_summary": requirement_summary,
            "current_stage": _field(stage_transition, "current_stage")
            or lead_profile.get("current_stage"),
            "previous_stage": _field(stage_transition, "previous_stage")
            or lead_profile.get("previous_stage"),
            "stage_before_objection": _field(stage_transition, "stage_before_objection")
            or lead_profile.get("stage_before_objection"),
            "conversation_mode": _field(stage_transition, "conversation_mode")
            or lead_profile.get("conversation_mode"),
            "last_action": lead_profile.get("last_action"),
        }
    )
    objection = _as_dict(active_objection) or dict(lead_profile.get("active_objection") or {})
    if objection.get("active") and not objection.get("resolved"):
        result["active_objection"] = _drop_empty(
            {
                "type": objection.get("type"),
                "strength": objection.get("strength"),
                "status": objection.get("status"),
                "relation": objection.get("relation"),
                "current_step": objection.get("current_step"),
                "paused": objection.get("paused"),
                "stage_before_objection": objection.get("stage_before_objection"),
            }
        )
    return result


def _compact_memory_context(
    structured_memory: Dict[str, Any],
    conversation_memory_evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return _drop_empty(
        {
            "known_slots": structured_memory.get("known_slots") or {},
            "missing_slots": structured_memory.get("missing_slots") or [],
            "forbidden_question_keys": structured_memory.get("forbidden_question_keys") or [],
            "conversation_memory_evidence": conversation_memory_evidence[:3],
        }
    )


def _compact_requirement_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    return _drop_empty(
        {
            "requirement_class": profile.get("requirement_class"),
            "active_informational_capabilities": _active_requirement_types(
                profile.get("informational_capabilities")
            ),
            "active_external_actions": _active_requirement_types(profile.get("external_actions")),
            "inactive_informational_capabilities": _inactive_requirement_types(
                profile.get("informational_capabilities")
            ),
            "inactive_external_actions": _inactive_requirement_types(profile.get("external_actions")),
        }
    )


def _active_requirement_types(entries: Any) -> List[str]:
    return [
        str(entry.get("type"))
        for entry in entries or []
        if isinstance(entry, dict) and entry.get("type") and entry.get("active", True)
    ][:5]


def _inactive_requirement_types(entries: Any) -> List[str]:
    return [
        str(entry.get("type"))
        for entry in entries or []
        if isinstance(entry, dict) and entry.get("type") and not entry.get("active", True)
    ][:5]


def _compact_turn_signal_context(normalized_turn: Dict[str, Any]) -> Dict[str, Any]:
    if not normalized_turn:
        return {}
    return _drop_empty(
        {
            "explicit_start_intent": normalized_turn.get("explicit_start_intent"),
            "is_post_purchase": normalized_turn.get("is_post_purchase"),
            "action_requirement": normalized_turn.get("action_requirement"),
            "active_product_context": normalized_turn.get("active_product_context"),
            "referenced_product": normalized_turn.get("referenced_product"),
            "requested_product": normalized_turn.get("requested_product"),
            "recommended_product": normalized_turn.get("recommended_product"),
            "selected_product": normalized_turn.get("selected_product"),
            "product_preference_mismatch": normalized_turn.get("product_preference_mismatch"),
            "observed_business_problems": normalized_turn.get("observed_business_problems") or [],
            "requested_agent_capabilities": normalized_turn.get("requested_agent_capabilities") or [],
            "requested_agent_actions": normalized_turn.get("requested_agent_actions") or [],
            "declared_external_action_count": normalized_turn.get("declared_external_action_count"),
            "current_turn_requirement_delta": normalized_turn.get("current_turn_requirement_delta") or {},
            "requirement_class": normalized_turn.get("requirement_class"),
            "requirement_profile": _compact_requirement_profile(
                normalized_turn.get("requirement_profile") or {}
            ),
            "confirmed_product": normalized_turn.get("confirmed_product"),
            "scope_flags": normalized_turn.get("scope_flags") or [],
            "unsupported_scope": normalized_turn.get("unsupported_scope"),
            "custom_scope_review_required": normalized_turn.get("custom_scope_review_required"),
            "product_unavailable": normalized_turn.get("product_unavailable"),
            "requested_capabilities": normalized_turn.get("requested_capabilities") or [],
            "requested_actions": normalized_turn.get("requested_actions") or [],
            "known_slots": normalized_turn.get("known_slots") or [],
            "missing_slots": normalized_turn.get("missing_slots") or [],
            "normalized_objection": normalized_turn.get("normalized_objection") or {},
            "objection_relation": normalized_turn.get("objection_relation"),
        }
    )


def _claim_constraints(normalized_turn: Dict[str, Any]) -> Dict[str, Any]:
    constraints: Dict[str, Any] = {
        "channels": {
            "available_now": ["whatsapp_business"],
            "upcoming_not_available": ["facebook", "instagram"],
            "forbidden": [
                "No digas que Facebook está disponible actualmente.",
                "No digas que Instagram está disponible actualmente.",
                "No describas MovIA como multicanal hoy.",
            ],
        },
        "products": {
            "available_now": ["movia_captura", "movia_hibrido"],
            "not_available": ["movia_ventas", "movia_pro_comercial"],
        },
        "captura_scope": {
            "allowed": [
                "recopilar informacion de pedidos dentro de WhatsApp",
                "entender texto, audio e imagenes si se configura",
            ],
            "forbidden": [
                "crear pedidos en sistemas externos",
                "registrar pedidos en sistemas externos",
                "escribir datos en sistemas externos",
                "decir que Captura no entiende audios",
            ],
        },
    }
    if (normalized_turn.get("requested_actions") or []) or normalized_turn.get("action_requirement") == "external_actions_required":
        constraints["external_action_routing"] = {
            "required_product": "movia_hibrido",
            "forbidden_product": "movia_captura",
        }
    if normalized_turn.get("requested_product") in {"movia_ventas", "movia_pro_comercial"}:
        constraints["requested_product_availability"] = {
            "requested_product": normalized_turn.get("requested_product"),
            "status": "not_available",
        }
    return constraints


def _official_product_response_requirements(
    official_facts: Dict[str, Any],
    normalized_turn: Dict[str, Any],
) -> List[str]:
    products = list(official_facts.get("products") or [])
    active_product = (
        normalized_turn.get("active_product_context")
        or normalized_turn.get("selected_product")
        or normalized_turn.get("confirmed_product")
        or normalized_turn.get("requested_product")
    )
    requirements: List[str] = []
    if active_product in {"movia_captura", "movia_hibrido"}:
        requirements.append(
            f"Si la pregunta es de precio, pago inicial o inicio y no menciona otro producto, responde usando active_product_context={active_product}."
        )
    for product in products:
        slug = str(product.get("slug") or "")
        if active_product and slug != active_product:
            continue
        capability_facts = product.get("capability_facts") or []
        if not capability_facts:
            continue
        if slug == "movia_captura" and any(
            "audio" in str(fact).lower() for fact in capability_facts
        ):
            requirements.append(
                "Si respondes sobre Captura y audio, afirma que Captura puede entender texto, audio e imágenes si se configura; no digas que no entiende audios."
            )
        if slug == "movia_captura":
            requirements.append(
                "Captura sirve para recopilar información dentro de WhatsApp; no la presentes como agente que escribe en sistemas externos."
            )
        if len(requirements) >= 2:
            break
    return requirements


def _payment_response_requirements(
    sales_plan: SalesPlan,
    official_facts: Dict[str, Any],
) -> List[str]:
    policies = official_facts.get("policies") or {}
    if not policies:
        return []
    relevant = sales_plan.macro_action in {
        MacroAction.DIRECT_CLOSE.value,
        MacroAction.EXPLAIN_PROCESS.value,
        MacroAction.ANSWER_AND_ADVANCE.value,
        MacroAction.RISK_REVERSAL.value,
    }
    has_payment_policy = any(
        key in policies
        for key in ["deposit_percentage", "final_payment_percentage", "refunds_allowed"]
    )
    if not relevant or not has_payment_policy:
        return []
    return [
        "Para empezar, no digas que el setup total es el pago inicial: el depósito es 50% del setup y el 50% restante se paga después de aprobar el agente.",
        "Si la pregunta es sobre demo, no mezcles el demo con el depósito: el demo limitado no requiere depósito y no inicia trabajo personalizado.",
        "Si hablas de reembolso o depósito, indica que el depósito no es reembolsable cuando esa política esté en official_facts.",
    ]


def _post_purchase_gate_response_requirements(
    sales_plan: SalesPlan,
    purchase_status: Dict[str, Any],
) -> List[str]:
    if not (
        sales_plan.macro_action == MacroAction.EXPLAIN_PROCESS.value
        and sales_plan.micro_action == MicroAction.EXPLAIN_HUMAN_HANDOFF.value
    ):
        return []
    return [
        "No contradigas ni acuses al usuario sobre el pago.",
        "Explica que el seguimiento personalizado queda disponible una vez que el depósito esté confirmado en la plataforma.",
        "Ofrece ayudar por este chat con dudas del proceso mientras tanto.",
    ]


def _requirement_profile_response_requirements(normalized_turn: Dict[str, Any]) -> List[str]:
    profile = normalized_turn.get("requirement_profile") or {}
    compact = _compact_requirement_profile(profile)
    inactive = (
        compact.get("inactive_informational_capabilities") or []
    ) + (compact.get("inactive_external_actions") or [])
    active = (
        compact.get("active_informational_capabilities") or []
    ) + (compact.get("active_external_actions") or [])
    requirements: List[str] = []
    if active or inactive:
        requirements.append(
            "El perfil de requisitos activo tiene prioridad sobre mensajes anteriores si hay contradicción."
        )
    if inactive:
        requirements.append(
            "No recomiendes ni justifiques producto usando requisitos inactivos o reemplazados: "
            + ", ".join(inactive[:4])
            + "."
        )
    return requirements


def _fulfillment_response_requirements(
    response_fulfillment_policy: Dict[str, Any],
) -> List[str]:
    if not response_fulfillment_policy:
        return []
    requirements: List[str] = []
    mandatory = set(response_fulfillment_policy.get("mandatory_fulfillments") or [])
    if "official_app_link" in mandatory:
        requirements.append(
            "Incluye el link oficial de la app desde official_facts. No lo sustituyas por un link inventado."
        )
    policy = response_fulfillment_policy.get("next_question_policy")
    if policy == NEXT_QUESTION_REPLACE_MINIMAL:
        question = minimal_question_for(response_fulfillment_policy)
        if question:
            requirements.append(
                "Usa esta pregunta mínima como continuación y no hagas una pregunta amplia de discovery: "
                + question
            )
    elif policy == NEXT_QUESTION_SUPPRESS:
        requirements.append(
            "No cierres con una pregunta de discovery; cumple la petición explícita y deja el cierre ligero."
        )
    return requirements


def _compact_official_facts(structured_context: Dict[str, Any]) -> Dict[str, Any]:
    facts: Dict[str, Any] = {}
    products = structured_context.get("products") or []
    if products:
        facts["products"] = [_compact_product(product) for product in products]
    policies = _compact_policies(structured_context.get("policies") or {})
    if policies:
        facts["policies"] = policies
    links = structured_context.get("official_links") or []
    app_link = next(
        (
            link.get("url")
            for link in links
            if link.get("link_type") == "app" or "app" in str(link.get("slug") or "")
        ),
        None,
    )
    if app_link:
        facts["official_links"] = {"app": app_link}
    if structured_context.get("project_statuses"):
        facts["project_statuses"] = [
            _drop_empty(
                {
                    "slug": status.get("slug"),
                    "label": status.get("label"),
                    "terminal": status.get("is_terminal"),
                }
            )
            for status in structured_context["project_statuses"][:5]
        ]
    return facts


def _compact_product(product: Dict[str, Any]) -> Dict[str, Any]:
    slug = str(product.get("slug") or _slug_for_name(product.get("name") or ""))
    compact = _drop_empty(
        {
            "slug": slug,
            "name": product.get("name"),
            "status": product.get("status"),
            "setup_price_mxn": product.get("setup_price_mxn"),
            "monthly_price_mxn": product.get("monthly_price_mxn"),
            "delivery_time": product.get("delivery_time"),
            "summary": product.get("short_description"),
        }
    )
    if "captura" in slug:
        compact["external_actions"] = False
    if "hibrido" in slug or "híbrido" in slug:
        compact["external_actions"] = True
        compact["max_actions"] = 2
    if product.get("status") != "available":
        compact["availability_note"] = "not_available"
    feature_facts = _compact_product_features(product.get("features") or [])
    if feature_facts:
        compact["capability_facts"] = feature_facts
    return compact


def _compact_product_features(features: List[Dict[str, Any]]) -> List[str]:
    facts: List[str] = []
    for feature in features:
        content = str(feature.get("content") or "").strip()
        if not content:
            continue
        lowered = content.lower()
        if any(term in lowered for term in ["audio", "imagen", "imágenes", "whatsapp", "pedido", "cita", "extern"]):
            facts.append(_truncate_text(content, 140))
        if len(facts) >= 4:
            break
    return facts


def _compact_policies(policies: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(policies, dict):
        return {}
    return _drop_empty(
        {
            "deposit_percentage": _policy_value(policies, "deposit", "percentage"),
            "deposit_required": _policy_value(policies, "deposit", "required"),
            "refunds_allowed": _policy_value(policies, "refund_policy", "refunds_allowed"),
            "final_payment_percentage": _policy_value(policies, "final_payment", "percentage"),
            "monthly_starts_when": _policy_value(policies, "monthly_billing", "starts_when"),
            "non_payment_result": _policy_value(policies, "monthly_billing", "non_payment_result"),
            "api_tokens_included": _policy_value(policies, "api_tokens", "included"),
            "api_tokens_fair_use": _policy_value(policies, "api_tokens", "fair_use"),
        }
    )


def _policy_value(policies: Dict[str, Any], slug: str, key: str) -> Any:
    policy = policies.get(slug) or {}
    if not isinstance(policy, dict):
        return None
    if key in policy:
        return policy.get(key)
    data = policy.get("data") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = {}
    if isinstance(data, dict):
        return data.get(key)
    return None


def _compact_playbook_instruction(
    analysis: TurnAnalysis,
    sales_plan: SalesPlan,
    json_context: Dict[str, Any],
) -> Dict[str, Any]:
    playbook: Dict[str, Any] = {
        "sales_action": _selected_sales_action(json_context, sales_plan.macro_action),
        "micro_action": _drop_empty(
            {
                "id": sales_plan.micro_action,
                "goal": sales_plan.commercial_goal,
                "next_question": sales_plan.next_question,
                "next_question_key": sales_plan.next_question_key,
            }
        ),
        "cta": _selected_cta(json_context, sales_plan),
        "tone": _selected_tone(json_context),
    }
    objection = _selected_objection(json_context, analysis)
    if objection:
        playbook["objection"] = objection
    overlay = _as_dict(sales_plan.objection_overlay)
    if overlay:
        playbook["objection_overlay"] = _drop_empty(
            {
                "mode": overlay.get("mode"),
                "relation": overlay.get("relation"),
                "type": overlay.get("type"),
                "strength": overlay.get("strength"),
                "status": overlay.get("status"),
                "current_step": overlay.get("current_step"),
                "inline": overlay.get("inline"),
                "blocking_close": overlay.get("blocking_close"),
                "response_instruction": overlay.get("response_instruction"),
            }
        )
    process = _selected_process(json_context, sales_plan, analysis)
    if process:
        playbook["process"] = process
    handoff = json_context.get("post_purchase_handoff")
    if isinstance(handoff, dict) and handoff.get("message"):
        playbook["post_purchase_handoff"] = {"message": handoff["message"]}
    comparison = _selected_source_routing(json_context, analysis)
    if comparison:
        playbook["source_routing"] = comparison
    return _drop_empty(playbook)


def _selected_sales_action(json_context: Dict[str, Any], macro_action: str) -> Dict[str, Any]:
    actions = (json_context.get("sales_actions") or {}).get("actions") or []
    selected = next((item for item in actions if item.get("id") == macro_action), None)
    return _drop_empty(
        {
            "id": macro_action,
            "description": (selected or {}).get("description"),
        }
    )


def _selected_cta(json_context: Dict[str, Any], sales_plan: SalesPlan) -> Dict[str, Any]:
    rules = json_context.get("cta_rules") or {}
    cta_type = sales_plan.cta_type
    key_by_type = {
        CTAType.DIRECT_CLOSE.value: "direct_close",
        CTAType.SEND_APP_LINK.value: "direct_close",
        CTAType.SOFT_CLOSE.value: "soft_close",
        CTAType.ASK_PERMISSION_TO_SEND_LINK.value: "soft_close",
        CTAType.DISCOVERY_QUESTION.value: "discovery_question",
        CTAType.SOFT_QUESTION.value: "discovery_question",
    }
    key = key_by_type.get(cta_type)
    return _drop_empty(
        {
            "type": cta_type,
            "text": rules.get(key) if key else None,
            "app_link": rules.get("app_link"),
        }
    )


def _selected_tone(json_context: Dict[str, Any]) -> Dict[str, Any]:
    tone = json_context.get("tone_rules") or {}
    return _drop_empty(
        {
            "tone": tone.get("tone"),
            "style": (tone.get("style") or [])[:2],
            "avoid": (tone.get("avoid") or [])[:3],
        }
    )


def _selected_objection(json_context: Dict[str, Any], analysis: TurnAnalysis) -> Dict[str, Any]:
    objections = (json_context.get("objection_playbook") or {}).get("objections") or {}
    if not objections:
        return {}
    objection_type = analysis.objection_type
    selected_type = objection_type if objection_type in objections else next(iter(objections.keys()))
    entry = objections.get(selected_type) or {}
    return _drop_empty(
        {
            "type": selected_type,
            "flow": (json_context.get("objection_playbook") or {}).get("methodology"),
            "first_response_goal": entry.get("first_response_goal"),
            "first_question": entry.get("first_question"),
            "signals": (entry.get("signals") or [])[:2],
        }
    )


def _selected_process(
    json_context: Dict[str, Any],
    sales_plan: SalesPlan,
    analysis: TurnAnalysis,
) -> Dict[str, Any]:
    steps = (json_context.get("platform_steps") or {}).get("steps") or []
    if not steps:
        return {}
    selected_indexes: List[int]
    if sales_plan.macro_action == MacroAction.DIRECT_CLOSE.value:
        selected_indexes = [0, 2, 3, 4, 8]
    elif Topic.DOCUMENTS.value in analysis.topics:
        selected_indexes = [9, 10, 12, 14]
    elif Topic.ONBOARDING.value in analysis.topics or sales_plan.macro_action == MacroAction.EXPLAIN_PROCESS.value:
        selected_indexes = [0, 2, 3, 5, 8]
    else:
        selected_indexes = [0, 3, 8]
    selected_steps = [steps[index] for index in selected_indexes if index < len(steps)]
    return _drop_empty(
        {
            "app_link": (json_context.get("platform_steps") or {}).get("app_link"),
            "steps": selected_steps,
        }
    )


def _selected_source_routing(json_context: Dict[str, Any], analysis: TurnAnalysis) -> Dict[str, Any]:
    if Topic.COMPETITOR_COMPARISON.value not in analysis.topics:
        return {}
    rules = (json_context.get("source_routing_rules") or {}).get("rules") or []
    selected = next((rule for rule in rules if rule.get("condition") == "comparison_question"), None)
    return _drop_empty(
        {
            "condition": (selected or {}).get("condition"),
            "sources": (selected or {}).get("sources"),
            "rag": (selected or {}).get("rag"),
        }
    )


def _compact_rag_context(
    rag_context: List[Dict[str, Any]],
    max_chunks: int = 3,
    max_chars_per_chunk: int = 650,
    total_chars: int = 1500,
) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    seen = set()
    used_chars = 0
    for chunk in rag_context or []:
        key = (chunk.get("source_path"), chunk.get("title"))
        if key in seen:
            continue
        seen.add(key)
        content = str(chunk.get("content") or chunk.get("preview") or "")
        remaining = max(0, total_chars - used_chars)
        if remaining <= 0 or len(compact) >= max_chunks:
            break
        preview = _truncate_text(content, min(max_chars_per_chunk, remaining))
        used_chars += len(preview)
        compact.append(
            _drop_empty(
                {
                    "title": chunk.get("title"),
                    "source_path": chunk.get("source_path"),
                    "metadata": _compact_rag_metadata(chunk.get("metadata") or {}),
                    "preview": preview,
                }
            )
        )
    return compact


def _compact_rag_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "topic",
        "industry",
        "comparison",
        "comparison_target",
        "product_explanation",
        "product",
        "faq",
        "source_type",
    }
    return {key: metadata[key] for key in allowed if key in metadata}


def _select_recent_messages(
    recent_messages: List[Dict[str, Any]],
    analysis: TurnAnalysis,
    lead_context: Dict[str, Any],
    max_messages: int = 4,
    max_chars: int = 220,
) -> List[Dict[str, Any]]:
    if not recent_messages:
        return []
    terms = _relevance_terms(analysis, lead_context)
    selected: List[Dict[str, Any]] = []
    for recency_index, message in enumerate(reversed(recent_messages[-8:])):
        content = str(message.get("content") or "")
        role = str(message.get("role") or "")
        if not content or not role:
            continue
        include = recency_index < 2 or (
            role == "user" and _is_relevant_message(content, terms)
        )
        if include:
            selected.append(
                {
                    "role": role,
                    "content": _truncate_text(content, max_chars),
                }
            )
        if len(selected) >= max_messages:
            break
    return list(reversed(selected))


def _relevance_terms(analysis: TurnAnalysis, lead_context: Dict[str, Any]) -> List[str]:
    terms = []
    for value in [
        lead_context.get("business_type"),
        lead_context.get("main_channel"),
        lead_context.get("pain"),
        analysis.business_type,
        analysis.main_channel,
        analysis.pain,
        *list(analysis.topics or []),
    ]:
        for part in str(value or "").replace("_", " ").lower().split():
            if len(part) >= 5:
                terms.append(part)
    terms.extend(["captura", "hibrido", "híbrido", "precio", "deposito", "depósito"])
    return list(dict.fromkeys(terms))


def _is_relevant_message(content: str, terms: List[str]) -> bool:
    lowered = content.lower()
    return any(term in lowered for term in terms)


def _products_from_context(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    structured_context = context.get("structured_context") or {}
    if structured_context.get("products"):
        return structured_context["products"]
    facts = context.get("official_facts") or {}
    return list(facts.get("products") or [])


def _field(value: Optional[Any], key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _as_dict(value: Optional[Any]) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _drop_empty(values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if value not in (None, "", [], {})
    }


def _slug_for_name(name: str) -> str:
    return name.lower().replace(" ", "-").replace("í", "i")


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    truncated = value[: max(0, max_chars - 1)].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated + "…"
