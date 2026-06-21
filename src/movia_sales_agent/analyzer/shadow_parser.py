from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from movia_sales_agent.analyzer.contract_v3 import (
    AnalyzerReferenceType,
    ObservedBusinessProblem,
    RequestedAgentAction,
    RequestedAgentCapability,
    RequestedProduct,
)
from movia_sales_agent.contracts.commercial import BuyingSignal


class ParserCandidate(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    type: str
    evidence_span: str


class ShadowParserResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shadow_parser_may_observe: bool = True
    shadow_parser_may_override: bool = False
    shadow_parser_may_choose_product: bool = False
    shadow_parser_may_choose_action: bool = False
    observed_problem_candidates: List[ParserCandidate] = Field(default_factory=list)
    requested_capability_candidates: List[ParserCandidate] = Field(default_factory=list)
    requested_action_candidates: List[ParserCandidate] = Field(default_factory=list)
    action_candidates: List[ParserCandidate] = Field(default_factory=list)
    product_candidates: List[ParserCandidate] = Field(default_factory=list)
    purchase_cue_candidates: List[ParserCandidate] = Field(default_factory=list)
    prior_reference_candidates: List[ParserCandidate] = Field(default_factory=list)
    channel_candidates: List[str] = Field(default_factory=list)
    negation_candidates: List[str] = Field(default_factory=list)


class ShadowSignalParser:
    def parse(self, message: str) -> ShadowParserResult:
        normalized = _normalize(message)
        requested_action_candidates = _dedupe_candidates(_action_candidates(message, normalized))
        return ShadowParserResult(
            observed_problem_candidates=_dedupe_candidates(_observed_problem_candidates(message, normalized)),
            requested_capability_candidates=_dedupe_candidates(_requested_capability_candidates(message, normalized)),
            requested_action_candidates=requested_action_candidates,
            action_candidates=requested_action_candidates,
            product_candidates=_dedupe_candidates(_product_candidates(message, normalized)),
            purchase_cue_candidates=_dedupe_candidates(_purchase_cues(message, normalized)),
            prior_reference_candidates=_dedupe_candidates(_prior_references(message, normalized)),
            channel_candidates=_dedupe_strings(_channel_candidates(normalized)),
            negation_candidates=_dedupe_strings(_negation_candidates(message, normalized)),
        )


def _action_candidates(message: str, normalized: str) -> List[ParserCandidate]:
    candidates: List[ParserCandidate] = []
    rules: Sequence[Tuple[str, Sequence[str]]] = [
        (RequestedAgentAction.SCHEDULE_APPOINTMENT.value, ["agendar", "agende", "agenda", "citas", "cita"]),
        (RequestedAgentAction.GENERATE_QUOTE.value, ["cotice", "cotizar", "cotizacion", "cotización"]),
        (RequestedAgentAction.CREATE_ORDER.value, ["registre pedidos", "registrar pedidos", "crear pedido", "pedidos"]),
        (RequestedAgentAction.READ_EXTERNAL_SYSTEM.value, ["leer mi sistema", "consultar sistema", "revisar sistema"]),
        (RequestedAgentAction.WRITE_EXTERNAL_SYSTEM.value, ["en mi sistema", "al sistema", "suba a mi panel", "subir datos"]),
        (RequestedAgentAction.UPDATE_EXTERNAL_RECORD.value, ["actualizar registro", "actualice", "editar registro"]),
        (RequestedAgentAction.SEND_REMINDER.value, ["recordatorio", "recordatorios", "recordar"]),
        (RequestedAgentAction.FOLLOW_UP_LEAD.value, ["seguimiento", "dar seguimiento", "follow up"]),
        (RequestedAgentAction.SEND_NOTIFICATION.value, ["notificar", "mande aviso", "enviar aviso"]),
        (RequestedAgentAction.TAKE_PAYMENT.value, ["cobrar", "tomar pago", "recibir pago"]),
    ]
    for action, phrases in rules:
        span = _first_span(message, normalized, phrases)
        if span:
            candidates.append(ParserCandidate(type=action, evidence_span=span))
    if "sistema" in normalized and not any(candidate.type == RequestedAgentAction.WRITE_EXTERNAL_SYSTEM.value for candidate in candidates):
        candidates.append(ParserCandidate(type=RequestedAgentAction.UNKNOWN_EXTERNAL_ACTION.value, evidence_span=_first_span(message, normalized, ["sistema"]) or message))
    return candidates


def _requested_capability_candidates(message: str, normalized: str) -> List[ParserCandidate]:
    candidates: List[ParserCandidate] = []
    rules: Sequence[Tuple[str, Sequence[str]]] = [
        (RequestedAgentCapability.ANSWER_CUSTOMER_QUESTIONS.value, ["responda dudas", "responder dudas", "contestar preguntas"]),
        (RequestedAgentCapability.PROVIDE_PRICES.value, ["de precios", "dar precios", "precios automaticamente", "precios automáticamente"]),
        (RequestedAgentCapability.CAPTURE_LEAD_DATA.value, ["capture datos", "capturar datos", "capture leads"]),
        (RequestedAgentCapability.EXPLAIN_BUSINESS_PROCESS.value, ["explique el proceso", "explique como funciona", "explique cómo funciona"]),
        (RequestedAgentCapability.CLOSE_SALE.value, ["cierre ventas", "cerrar ventas", "venda por mi", "venda por mí"]),
    ]
    for capability, phrases in rules:
        span = _first_span(message, normalized, phrases)
        if span:
            candidates.append(ParserCandidate(type=capability, evidence_span=span))
    return candidates


def _observed_problem_candidates(message: str, normalized: str) -> List[ParserCandidate]:
    candidates: List[ParserCandidate] = []
    rules: Sequence[Tuple[str, Sequence[str]]] = [
        (ObservedBusinessProblem.LEAD_DROP_OFF.value, ["desaparecen", "pierdo leads", "se pierden leads", "se enfria", "se enfría"]),
        (ObservedBusinessProblem.SLOW_RESPONSE.value, ["no responden", "nadie contesta", "nadie responde"]),
        (ObservedBusinessProblem.MANUAL_SCHEDULING.value, ["agendamos manualmente", "agenda todo manualmente"]),
        (ObservedBusinessProblem.MANUAL_DATA_CAPTURE.value, ["capturamos manualmente", "registramos manualmente"]),
        (ObservedBusinessProblem.REPETITIVE_QUESTIONS.value, ["mismas preguntas", "siempre preguntan"]),
    ]
    for problem, phrases in rules:
        span = _first_span(message, normalized, phrases)
        if span:
            candidates.append(ParserCandidate(type=problem, evidence_span=span))
    return candidates


def _product_candidates(message: str, normalized: str) -> List[ParserCandidate]:
    candidates = []
    rules = [
        (RequestedProduct.MOVIA_CAPTURA.value, ["movia captura", "captura"]),
        (RequestedProduct.MOVIA_HIBRIDO.value, ["movia hibrido", "movia híbrido", "hibrido", "híbrido"]),
        (RequestedProduct.MOVIA_VENTAS.value, ["movia ventas", "ventas"]),
        (RequestedProduct.MOVIA_PRO_COMERCIAL.value, ["pro comercial", "movia pro"]),
    ]
    for product, phrases in rules:
        span = _first_span(message, normalized, phrases)
        if span:
            candidates.append(ParserCandidate(type=product, evidence_span=span))
    return candidates


def _purchase_cues(message: str, normalized: str) -> List[ParserCandidate]:
    candidates = []
    explicit = [
        "pasame el link",
        "pásame el link",
        "mandame el link",
        "mándame el link",
        "quiero empezar",
        "quiero iniciar",
        "quiero contratar",
        "donde pago",
        "dónde pago",
    ]
    high = ["me interesa", "suena bien", "me convenciste", "quiero avanzar"]
    span = _first_span(message, normalized, explicit)
    if span:
        candidates.append(ParserCandidate(type=BuyingSignal.EXPLICIT_START.value, evidence_span=span))
    span = _first_span(message, normalized, high)
    if span:
        candidates.append(ParserCandidate(type=BuyingSignal.HIGH.value, evidence_span=span))
    return candidates


def _prior_references(message: str, normalized: str) -> List[ParserCandidate]:
    candidates = []
    rules = [
        (AnalyzerReferenceType.IMPLICIT_PRIOR_REFERENCE.value, ["como te dije", "como dije", "hace rato", "al inicio"]),
        (AnalyzerReferenceType.TOPIC_REFERENCE.value, ["lo de", "lo que te comente", "lo que te comenté"]),
        (AnalyzerReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value, ["tu dijiste", "tú dijiste", "me dijiste", "me recomendaste"]),
    ]
    for reference_type, phrases in rules:
        span = _first_span(message, normalized, phrases)
        if span:
            candidates.append(ParserCandidate(type=reference_type, evidence_span=span))
    return candidates


def _channel_candidates(normalized: str) -> List[str]:
    return [
        channel
        for channel in ["whatsapp", "facebook", "instagram"]
        if channel in normalized
    ]


def _negation_candidates(message: str, normalized: str) -> List[str]:
    phrases = ["no quiero", "no necesito", "sin", "nunca", "no me sirve"]
    return [span for phrase in phrases if (span := _first_span(message, normalized, [phrase]))]


def _first_span(message: str, normalized: str, phrases: Iterable[str]) -> Optional[str]:
    for phrase in phrases:
        normalized_phrase = _normalize(phrase)
        if normalized_phrase not in normalized:
            continue
        match = re.search(re.escape(normalized_phrase), normalized)
        if not match:
            return phrase
        return _substring_by_normalized_offsets(message, match.start(), match.end()) or phrase
    return None


def _substring_by_normalized_offsets(message: str, start: int, end: int) -> Optional[str]:
    normalized_chars = []
    source_indexes = []
    for index, char in enumerate(message):
        normalized = _normalize(char)
        if not normalized:
            continue
        for normalized_char in normalized:
            normalized_chars.append(normalized_char)
            source_indexes.append(index)
    if start >= len(source_indexes) or end <= 0:
        return None
    source_start = source_indexes[start]
    source_end = source_indexes[min(end - 1, len(source_indexes) - 1)] + 1
    return message[source_start:source_end].strip(" ¿?.,;:!¡")


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"[^\w\s%]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _dedupe_candidates(candidates: List[ParserCandidate]) -> List[ParserCandidate]:
    seen = set()
    result = []
    for candidate in candidates:
        key = (candidate.type, candidate.evidence_span)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _dedupe_strings(values: List[str]) -> List[str]:
    result = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
