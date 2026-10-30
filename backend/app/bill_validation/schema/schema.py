from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ValidationAlert(BaseModel):
    code: str
    severity: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ValidatedLineItem(BaseModel):
    line_item_id: str | None
    raw_item_name: str
    billed_qty: int
    free_qty: int
    billed_rate: Decimal
    tax_percent: Decimal
    net_amount: Decimal
    gst_amount: Decimal
    expected_line_total: Decimal
    true_landed_cost: Decimal
    stored_true_landed_cost: Decimal | None


class InvoiceValidationResponse(BaseModel):
    invoice_id: str
    billed_total: Decimal
    recomputed_total: Decimal
    delta: Decimal
    is_valid: bool
    line_items: list[ValidatedLineItem]
    alerts: list[dict[str, Any]]


class InvoiceAlertsResponse(BaseModel):
    invoice_id: str
    alerts: list[dict[str, Any]]
