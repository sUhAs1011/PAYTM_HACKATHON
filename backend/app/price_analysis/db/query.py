import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


async def get_invoice(invoice_id: str) -> dict[str, Any] | None:
    from app.core.db import get_client

    client = await get_client()
    response = (
        await client.table("invoices")
        .select("*")
        .eq("id", invoice_id)
        .limit(1)
        .execute()
    )
    logger.debug("supabase_query_completed table=invoices row_count=%s", len(response.data or []))
    return response.data[0] if response.data else None


async def get_merchant(merchant_id: str) -> dict[str, Any] | None:
    from app.core.db import get_client

    client = await get_client()
    response = (
        await client.table("merchants")
        .select("id,pincode")
        .eq("id", merchant_id)
        .limit(1)
        .execute()
    )
    logger.debug("supabase_query_completed table=merchants row_count=%s", len(response.data or []))
    return response.data[0] if response.data else None


async def get_supplier(supplier_id: str) -> dict[str, Any] | None:
    from app.core.db import get_client

    client = await get_client()
    response = (
        await client.table("suppliers")
        .select("id")
        .eq("id", supplier_id)
        .limit(1)
        .execute()
    )
    logger.debug("supabase_query_completed table=suppliers row_count=%s", len(response.data or []))
    return response.data[0] if response.data else None


async def get_invoice_line_items(invoice_id: str) -> list[dict[str, Any]]:
    from app.core.db import get_client

    client = await get_client()
    response = (
        await client.table("invoice_line_items")
        .select("*")
        .eq("invoice_id", invoice_id)
        .execute()
    )
    logger.debug(
        "supabase_query_completed table=invoice_line_items row_count=%s",
        len(response.data or []),
    )
    return response.data or []


async def get_supplier_history(
    invoice: dict[str, Any], canonical_sku_id: str
) -> list[dict[str, Any]]:
    from app.core.db import get_client

    supplier_id = invoice.get("supplier_id")
    merchant_id = invoice.get("merchant_id")
    if not supplier_id or not merchant_id:
        return []

    client = await get_client()
    query = (
        client.table("invoices")
        .select("id,invoice_date")
        .eq("merchant_id", merchant_id)
        .eq("supplier_id", supplier_id)
        .neq("id", invoice["id"])
    )
    if invoice.get("invoice_date"):
        query = query.lt("invoice_date", str(invoice["invoice_date"]))
    invoices_response = await (
        query.order("invoice_date", desc=True).limit(500).execute()
    )
    previous = invoices_response.data or []
    logger.debug(
        "supabase_query_completed table=invoices operation=supplier_history row_count=%s",
        len(previous),
    )
    if not previous:
        return []

    invoice_dates = {str(row["id"]): row.get("invoice_date") for row in previous}
    line_response = (
        await client.table("invoice_line_items")
        .select("invoice_id,billed_rate,canonical_sku_id")
        .in_("invoice_id", list(invoice_dates))
        .eq("canonical_sku_id", canonical_sku_id)
        .execute()
    )
    lines = line_response.data or []
    logger.debug(
        "supabase_query_completed table=invoice_line_items operation=supplier_history row_count=%s",
        len(lines),
    )
    lines.sort(
        key=lambda line: str(invoice_dates.get(str(line["invoice_id"])) or ""),
        reverse=True,
    )

    rates = []
    seen_invoices = set()
    for line in lines:
        line_invoice_id = str(line["invoice_id"])
        if line_invoice_id in seen_invoices:
            continue
        seen_invoices.add(line_invoice_id)
        rates.append(
            {
                "invoice_id": line_invoice_id,
                "invoice_date": invoice_dates.get(line_invoice_id),
                "billed_rate": line["billed_rate"],
            }
        )
        if len(rates) == 3:
            break
    return rates


async def get_pincode_peer_rates(
    current_invoice: dict[str, Any],
    canonical_sku_id: str,
    pincode: str,
    start_date: date,
    end_date: date,
) -> list[tuple[str, Any]]:
    from app.core.db import get_client

    client = await get_client()
    merchant_response = (
        await client.table("merchants")
        .select("id")
        .eq("pincode", pincode)
        .neq("id", current_invoice["merchant_id"])
        .execute()
    )
    merchant_ids = [row["id"] for row in (merchant_response.data or [])]
    logger.debug(
        "supabase_query_completed table=merchants operation=pincode_peers row_count=%s",
        len(merchant_ids),
    )
    if not merchant_ids:
        return []

    invoices_response = (
        await client.table("invoices")
        .select("id,merchant_id")
        .in_("merchant_id", merchant_ids)
        # start_date is the exclusive boundary so the inclusive end date spans
        # exactly 14 calendar dates, not 15.
        .gt("invoice_date", start_date.isoformat())
        .lte("invoice_date", end_date.isoformat())
        .neq("id", current_invoice["id"])
        .limit(1000)
        .execute()
    )
    peer_invoices = invoices_response.data or []
    logger.debug(
        "supabase_query_completed table=invoices operation=pincode_peers row_count=%s",
        len(peer_invoices),
    )
    if not peer_invoices:
        return []
    invoice_merchants = {
        str(row["id"]): str(row["merchant_id"]) for row in peer_invoices
    }
    line_response = (
        await client.table("invoice_line_items")
        .select("invoice_id,billed_rate,canonical_sku_id")
        .in_("invoice_id", list(invoice_merchants))
        .eq("canonical_sku_id", canonical_sku_id)
        .execute()
    )
    logger.debug(
        "supabase_query_completed table=invoice_line_items operation=pincode_peers row_count=%s",
        len(line_response.data or []),
    )
    return [
        (invoice_merchants[str(line["invoice_id"])], line["billed_rate"])
        for line in (line_response.data or [])
        if str(line["invoice_id"]) in invoice_merchants
    ]
