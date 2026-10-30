from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

MONEY = Decimal("0.01")
ZERO = Decimal("0")


def as_decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field_name} must be a numeric value")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a numeric value") from exc
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LineCalculation:
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "line_item_id": self.line_item_id,
            "raw_item_name": self.raw_item_name,
            "billed_qty": self.billed_qty,
            "free_qty": self.free_qty,
            "billed_rate": self.billed_rate,
            "tax_percent": self.tax_percent,
            "net_amount": self.net_amount,
            "gst_amount": self.gst_amount,
            "expected_line_total": self.expected_line_total,
            "true_landed_cost": self.true_landed_cost,
            "stored_true_landed_cost": self.stored_true_landed_cost,
        }


def calculate_line(item: dict[str, Any]) -> LineCalculation:
    try:
        billed_qty = int(item["billed_qty"])
        free_qty = int(item.get("free_qty") or 0)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("billed_qty and free_qty must be integers") from exc
    if billed_qty < 0 or free_qty < 0:
        raise ValueError("quantities cannot be negative")
    units_received = billed_qty + free_qty
    if units_received == 0:
        raise ValueError("billed_qty plus free_qty must be greater than zero")

    rate = as_decimal(item["billed_rate"], "billed_rate")
    tax_percent = as_decimal(item.get("tax_percent", 0), "tax_percent")
    if rate < ZERO or tax_percent < ZERO:
        raise ValueError("rate and tax percentage cannot be negative")

    net_amount = money(Decimal(billed_qty) * rate)
    gst_amount = money(net_amount * tax_percent / Decimal("100"))
    expected_line_total = money(net_amount + gst_amount)
    landed_cost = money((net_amount + gst_amount) / Decimal(units_received))
    stored_value = item.get("true_landed_cost")

    return LineCalculation(
        line_item_id=str(item["id"]) if item.get("id") is not None else None,
        raw_item_name=str(item.get("raw_item_name") or ""),
        billed_qty=billed_qty,
        free_qty=free_qty,
        billed_rate=money(rate),
        tax_percent=tax_percent,
        net_amount=net_amount,
        gst_amount=gst_amount,
        expected_line_total=expected_line_total,
        true_landed_cost=landed_cost,
        stored_true_landed_cost=money(as_decimal(stored_value, "true_landed_cost"))
        if stored_value is not None
        else None,
    )


def validate_invoice(
    invoice: dict[str, Any], line_items: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    items = list(line_items)
    calculations = [calculate_line(item) for item in items]
    expected_total = money(sum((line.expected_line_total for line in calculations), ZERO))
    stored_total = money(as_decimal(invoice["billed_total"], "billed_total"))
    delta = money(expected_total - stored_total)
    alerts: list[dict[str, Any]] = []

    if abs(delta) >= MONEY:
        alerts.append(
            {
                "code": "TOTAL_MISMATCH",
                "severity": "HIGH",
                "message": "Recomputed invoice total does not match the stored billed total.",
                "expected_total": expected_total,
                "stored_total": stored_total,
                "delta": delta,
            }
        )

    if not calculations:
        alerts.append(
            {
                "code": "NO_LINE_ITEMS",
                "severity": "HIGH",
                "message": "No invoice line items were found for calculation.",
            }
        )

    for line in calculations:
        if (
            line.stored_true_landed_cost is not None
            and abs(line.true_landed_cost - line.stored_true_landed_cost) >= MONEY
        ):
            alerts.append(
                {
                    "code": "LANDED_COST_DRIFT",
                    "severity": "MEDIUM",
                    "line_item_id": line.line_item_id,
                    "message": "Stored true landed cost differs from the recomputed value.",
                    "expected": line.true_landed_cost,
                    "stored": line.stored_true_landed_cost,
                }
            )

    for item in items:
        confidence = item.get("ocr_confidence")
        if confidence is not None and as_decimal(confidence, "ocr_confidence") < Decimal("0.80"):
            alerts.append(
                {
                    "code": "LOW_OCR_CONFIDENCE",
                    "severity": "REVIEW",
                    "line_item_id": str(item.get("id")) if item.get("id") else None,
                    "message": "Confirm this line item before approving the bill.",
                }
            )

    return {
        "invoice_id": str(invoice["id"]),
        "billed_total": stored_total,
        "recomputed_total": expected_total,
        "delta": delta,
        "is_valid": not any(
            alert["code"] in {"TOTAL_MISMATCH", "NO_LINE_ITEMS"} for alert in alerts
        ),
        "line_items": [line.as_dict() for line in calculations],
        "alerts": alerts,
    }