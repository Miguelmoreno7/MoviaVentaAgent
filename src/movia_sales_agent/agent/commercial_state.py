from __future__ import annotations

from typing import Any, Dict, Optional


AVAILABLE_PRODUCTS = {"movia_captura", "movia_hibrido"}
UNAVAILABLE_PRODUCTS = {"movia_ventas", "movia_pro_comercial"}
KNOWN_PRODUCTS = AVAILABLE_PRODUCTS | UNAVAILABLE_PRODUCTS


def resolve_product_context(
    *,
    profile_data: Dict[str, Any],
    normalized_turn: Dict[str, Any],
    turn_number: int,
) -> Dict[str, Any]:
    """Keep reference, active context, and commitment as separate commercial facts."""
    previous = dict(profile_data.get("product_context") or {})
    references = _normalized_product_references(normalized_turn.get("product_references"))
    referenced_products = _dedupe_products(
        [reference["product"] for reference in references]
    )
    requested = (
        referenced_products[0]
        if len(referenced_products) == 1
        else _valid_product(normalized_turn.get("requested_product"))
    )
    selected = _valid_product(normalized_turn.get("selected_product"))
    confirmed = _valid_product(
        normalized_turn.get("confirmed_product") or profile_data.get("confirmed_product")
    )
    stored_selected = _valid_product(profile_data.get("selected_product"))

    active = _valid_product(
        previous.get("active_product_context") or profile_data.get("known_product_fit")
    )
    source = previous.get("source") or "none"
    question_subjects = _products_for_role(references, "question_subject")
    committed_references = _products_for_role(references, "committed")
    preferred_references = _products_for_role(references, "preferred")
    contextual_frame = dict(normalized_turn.get("contextual_reply_frame") or {})
    contextual_reply_act = str(normalized_turn.get("contextual_reply_act") or "")
    contextual_active = None
    if contextual_reply_act in {"accept", "provide_answer", "ask_followup"}:
        contextual_active = _valid_product(contextual_frame.get("target_product"))
    current_active = _single_product(
        question_subjects or committed_references or preferred_references
    )
    if current_active:
        active = current_active
        source = "current_reference"
    elif requested:
        active = requested
        source = "current_reference"
    elif contextual_active:
        active = contextual_active
        source = "planner_reply_frame"
    if selected:
        active = selected
        stored_selected = selected
        source = "explicit_commitment"
    if confirmed and not current_active and not contextual_active and not selected:
        active = confirmed
        source = "confirmed_product"

    return {
        "referenced_product": requested,
        "referenced_products": referenced_products,
        "last_referenced_products": referenced_products
        or list(previous.get("last_referenced_products") or []),
        "active_product_context": active,
        "selected_product": stored_selected,
        "confirmed_product": confirmed,
        "source": source,
        "last_updated_turn": turn_number
        if referenced_products or selected or confirmed
        else previous.get("last_updated_turn"),
    }


def committed_product(product_context: Dict[str, Any], profile_data: Dict[str, Any]) -> Optional[str]:
    return _valid_product(
        product_context.get("confirmed_product")
        or product_context.get("selected_product")
        or profile_data.get("confirmed_product")
        or profile_data.get("selected_product")
    )


def _valid_product(value: Any) -> Optional[str]:
    product = str(value or "").strip()
    if product in KNOWN_PRODUCTS:
        return product
    return None


def _normalized_product_references(value: Any) -> list[Dict[str, str]]:
    references: list[Dict[str, str]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        product = _valid_product(item.get("product"))
        role = str(item.get("reference_role") or "")
        if product and role:
            references.append({"product": product, "reference_role": role})
    return references


def _products_for_role(references: list[Dict[str, str]], role: str) -> list[str]:
    return _dedupe_products(
        [item["product"] for item in references if item.get("reference_role") == role]
    )


def _dedupe_products(products: list[str]) -> list[str]:
    result: list[str] = []
    for product in products:
        if product not in result:
            result.append(product)
    return result


def _single_product(products: list[str]) -> Optional[str]:
    return products[0] if len(products) == 1 else None
