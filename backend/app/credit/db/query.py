import logging
from datetime import datetime, timezone
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
        .select("*")
        .eq("id", merchant_id)
        .limit(1)
        .execute()
    )
    logger.debug("supabase_query_completed table=merchants row_count=%s", len(response.data or []))
    return response.data[0] if response.data else None


async def get_transactions(
    merchant_id: str,
    merchant_vpa: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    from app.core.db import get_client

    client = await get_client()
    query = (
        client.table("transactions")
        .select(
            "t_id,merchant_id,amount,payer_vpa,merchant_vpa,txn_status,created_at"
        )
        .eq("merchant_id", merchant_id)
        .eq("merchant_vpa", merchant_vpa)
        .neq("payer_vpa", merchant_vpa)
        .order("created_at")
    )
    if start is not None:
        query = query.gte("created_at", start.isoformat())
    if end is not None:
        # Seven-day simulation windows are [start, end), so a transaction on
        # a boundary belongs to exactly one cycle, not both adjacent weeks.
        query = query.lt("created_at", end.isoformat())
    results = []
    offset = 0
    page_size = 1000
    while True:
        response = await query.range(offset, offset + page_size - 1).execute()
        page = response.data or []
        results.extend(page)
        if len(page) < page_size:
            logger.debug(
                "supabase_query_completed table=transactions row_count=%s",
                len(results),
            )
            return results
        offset += page_size


async def get_active_loan(invoice_id: str) -> dict[str, Any] | None:
    from app.core.db import get_client

    client = await get_client()
    response = (
        await client.table("split_credit_loans")
        .select("*")
        .eq("invoice_id", invoice_id)
        .eq("status", "ACTIVE")
        .limit(1)
        .execute()
    )
    logger.debug("supabase_query_completed table=split_credit_loans row_count=%s", len(response.data or []))
    return response.data[0] if response.data else None


async def get_loan(loan_id: str) -> dict[str, Any] | None:
    from app.core.db import get_client

    client = await get_client()
    response = (
        await client.table("split_credit_loans")
        .select("*")
        .eq("id", loan_id)
        .limit(1)
        .execute()
    )
    logger.debug("supabase_query_completed table=split_credit_loans row_count=%s", len(response.data or []))
    return response.data[0] if response.data else None


async def create_loan(values: dict[str, Any]) -> dict[str, Any]:
    from app.core.db import get_client

    client = await get_client()
    response = await client.table("split_credit_loans").insert(values).execute()
    logger.info("supabase_write_completed table=split_credit_loans operation=insert row_count=%s", len(response.data or []))
    if not response.data:
        raise RuntimeError("Loan insert returned no row")
    return response.data[0]


async def update_loan(loan_id: str, values: dict[str, Any]) -> dict[str, Any]:
    from app.core.db import get_client

    client = await get_client()
    response = (
        await client.table("split_credit_loans")
        .update(values)
        .eq("id", loan_id)
        .execute()
    )
    logger.info("supabase_write_completed table=split_credit_loans operation=update row_count=%s", len(response.data or []))
    if not response.data:
        raise LookupError("Loan not found")
    return response.data[0]


async def get_loan_ledger(loan_id: str) -> list[dict[str, Any]]:
    from app.core.db import get_client

    client = await get_client()
    response = (
        await client.table("merchant_account_ledger")
        .select("*")
        .eq("loan_id", loan_id)
        .order("entry_ts")
        .execute()
    )
    logger.debug("supabase_query_completed table=merchant_account_ledger row_count=%s", len(response.data or []))
    return response.data or []


async def get_merchant_ledger(merchant_id: str) -> list[dict[str, Any]]:
    """Return the merchant's signed ledger rows (QR credits remain in transactions)."""
    from app.core.db import get_client

    client = await get_client()
    query = (
        client.table("merchant_account_ledger")
        .select("id,merchant_id,entry_ts,kind,amount,loan_id")
        .eq("merchant_id", merchant_id)
        .order("entry_ts")
    )
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        response = await query.range(offset, offset + page_size - 1).execute()
        page = response.data or []
        rows.extend(page)
        if len(page) < page_size:
            logger.debug(
                "supabase_query_completed table=merchant_account_ledger row_count=%s",
                len(rows),
            )
            return rows
        offset += page_size


async def create_ledger_entry(values: dict[str, Any]) -> dict[str, Any]:
    from app.core.db import get_client

    client = await get_client()
    values.setdefault("entry_ts", datetime.now(timezone.utc).isoformat())
    response = (
        await client.table("merchant_account_ledger")
        .insert(values)
        .execute()
    )
    logger.info("supabase_write_completed table=merchant_account_ledger operation=insert row_count=%s", len(response.data or []))
    if not response.data:
        raise RuntimeError("Ledger insert returned no row")
    return response.data[0]
