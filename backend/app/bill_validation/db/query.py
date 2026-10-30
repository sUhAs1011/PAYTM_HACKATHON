import logging
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
