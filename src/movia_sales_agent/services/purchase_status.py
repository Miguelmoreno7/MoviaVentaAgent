from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


PURCHASE_STATUS_DEPOSIT_CONFIRMED = "deposit_confirmed"
PURCHASE_STATUS_PAID_IN_FULL = "paid_in_full"
PURCHASE_STATUS_NOT_CHECKED = "not_checked"

HANDOFF_ALLOWED_STATUSES = {
    PURCHASE_STATUS_DEPOSIT_CONFIRMED,
    PURCHASE_STATUS_PAID_IN_FULL,
}


@dataclass(frozen=True)
class PurchaseStatusResult:
    status: str = PURCHASE_STATUS_NOT_CHECKED
    checked: bool = False
    source: str = "disabled"
    metadata: Optional[Dict[str, Any]] = None

    @property
    def handoff_allowed(self) -> bool:
        return self.status in HANDOFF_ALLOWED_STATUSES

    def model_dump(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "checked": self.checked,
            "source": self.source,
            "handoff_allowed": self.handoff_allowed,
            "metadata": self.metadata or {},
        }


class PurchaseStatusService:
    def get_purchase_status(
        self,
        *,
        channel: str,
        external_user_id: str,
        lead_profile: Optional[Dict[str, Any]] = None,
    ) -> PurchaseStatusResult:
        return PurchaseStatusResult(
            status=PURCHASE_STATUS_NOT_CHECKED,
            checked=False,
            source="disabled",
            metadata={
                "channel": channel,
                "external_user_id": external_user_id,
            },
        )


class FixedPurchaseStatusService(PurchaseStatusService):
    def __init__(self, status: str, *, source: str = "test"):
        self.status = status
        self.source = source

    def get_purchase_status(
        self,
        *,
        channel: str,
        external_user_id: str,
        lead_profile: Optional[Dict[str, Any]] = None,
    ) -> PurchaseStatusResult:
        return PurchaseStatusResult(
            status=self.status,
            checked=True,
            source=self.source,
            metadata={
                "channel": channel,
                "external_user_id": external_user_id,
            },
        )
