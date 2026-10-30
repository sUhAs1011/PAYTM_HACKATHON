import logging
from typing import Any

from app.bill_validation.db.query import get_invoice, get_invoice_line_items
from app.engine.math_engine import validate_invoice

logger = logging.getLogger(__name__)


async def validate_bill(invoice_id: str) -> dict[str, Any]:
    logger.info("bill_validation_started invoice_id=%s", invoice_id)
    invoice = await get_invoice(invoice_id)
    if invoice is None:
        logger.warning("bill_validation_invoice_missing invoice_id=%s", invoice_id)
        raise LookupError("Invoice not found")
    line_items = await get_invoice_line_items(invoice_id)
    logger.debug(
        "bill_validation_lines_loaded invoice_id=%s line_count=%s",
        invoice_id,
        len(line_items),
    )
    result = validate_invoice(invoice, line_items)
    logger.info(
        "bill_validation_completed invoice_id=%s is_valid=%s alert_codes=%s",
        invoice_id,
        result["is_valid"],
        ",".join(alert["code"] for alert in result["alerts"]),
    )
    return result


async def get_bill_alerts(invoice_id: str) -> dict[str, Any]:
    validation = await validate_bill(invoice_id)
    logger.debug(
        "bill_alerts_ready invoice_id=%s alert_count=%s",
        invoice_id,
        len(validation["alerts"]),
    )
    return {"invoice_id": validation["invoice_id"], "alerts": validation["alerts"]}
