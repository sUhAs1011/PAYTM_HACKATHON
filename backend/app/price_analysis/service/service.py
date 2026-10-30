import logging
from datetime import date, timedelta
from typing import Any

from app.engine.waterfall_engine import analyze_price
from app.price_analysis.db.query import (
    get_invoice,
    get_invoice_line_items,
    get_merchant,
    get_pincode_peer_rates,
    get_supplier_history,
    get_supplier,
)

logger = logging.getLogger(__name__)


async def analyze_invoice_prices(invoice_id: str) -> dict[str, Any]:
    logger.info("price_analysis_started invoice_id=%s", invoice_id)
    invoice = await get_invoice(invoice_id)
    if invoice is None:
        logger.warning("price_analysis_invoice_missing invoice_id=%s", invoice_id)
        raise LookupError("Invoice not found")
    merchant = await get_merchant(str(invoice["merchant_id"]))
    if merchant is None:
        logger.warning("price_analysis_merchant_missing invoice_id=%s", invoice_id)
        raise LookupError("Merchant not found")
    supplier_id = invoice.get("supplier_id")
    if supplier_id is not None and await get_supplier(str(supplier_id)) is None:
        logger.warning("price_analysis_supplier_missing invoice_id=%s", invoice_id)
        raise LookupError("Supplier not found")
    pincode = str(merchant["pincode"])
    line_items = await get_invoice_line_items(invoice_id)
    logger.debug(
        "price_analysis_lines_loaded invoice_id=%s line_count=%s",
        invoice_id,
        len(line_items),
    )
    benchmark_end = (
        date.fromisoformat(str(invoice["invoice_date"]))
        if invoice.get("invoice_date")
        else date.today()
    )
    benchmark_start = benchmark_end - timedelta(days=14)

    results = []
    peer_cache: dict[str, list[tuple[str, Any]]] = {}
    history_cache: dict[str, list[dict[str, Any]]] = {}
    for item in line_items:
        sku_id = item.get("canonical_sku_id")
        if sku_id is None:
            results.append(
                {
                    "line_item_id": str(item["id"]),
                    "item_name": item.get("raw_item_name", ""),
                    "canonical_sku_id": None,
                    "analysis": analyze_price(item["billed_rate"], [], []),
                }
            )
            continue
        sku_id = str(sku_id)
        if sku_id not in history_cache:
            history_cache[sku_id] = await get_supplier_history(invoice, sku_id)
        if sku_id not in peer_cache:
            peer_cache[sku_id] = await get_pincode_peer_rates(
                invoice, sku_id, pincode, benchmark_start, benchmark_end
            )
        analysis = analyze_price(
            item["billed_rate"],
            [row["billed_rate"] for row in history_cache[sku_id]],
            peer_cache[sku_id],
        )
        analysis["supplier_history"]["last_3_invoices"] = history_cache[sku_id]
        logger.debug(
            "price_analysis_item_completed invoice_id=%s peer_store_count=%s gate_active=%s rate_status=%s",
            invoice_id,
            analysis["pincode_benchmark"]["peer_store_count"],
            analysis["pincode_benchmark"]["gate_active"],
            analysis["rate_status"],
        )
        results.append(
            {
                "line_item_id": str(item["id"]),
                "item_name": item.get("raw_item_name", ""),
                "canonical_sku_id": sku_id,
                "analysis": analysis,
            }
        )

    result = {
        "invoice_id": str(invoice["id"]),
        "pincode": pincode,
        "items": results,
    }
    logger.info(
        "price_analysis_completed invoice_id=%s item_count=%s",
        invoice_id,
        len(results),
    )
    return result
