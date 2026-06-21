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
    requested = _valid_product(normalized_turn.get("requested_product"))
    selected = _valid_product(normalized_turn.get("selected_product"))
    confirmed = _valid_product(
        normalized_turn.get("confirmed_product") or profile_data.get("confirmed_product")
    )
    stored_selected = _valid_product(profile_data.get("selected_product"))

    active = _valid_product(previous.get("active_product_context"))
    source = previous.get("source") or "none"
    if requested:
        active = requested
        source = "current_reference"
    if selected:
        active = selected
        stored_selected = selected
        source = "explicit_commitment"
    if confirmed:
        active = confirmed
        source = "confirmed_product"

    return {
        "referenced_product": requested,
        "active_product_context": active,
        "selected_product": stored_selected,
        "confirmed_product": confirmed,
        "source": source,
        "last_updated_turn": turn_number if requested or selected or confirmed else previous.get("last_updated_turn"),
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
