"""Repository functions (Module 2 slice 1) — the only DB access in this slice.

Thin data access over PostgREST using the shared async client from
app.core.db (service_role secret key — bypasses RLS; financial tables are
backend-owned). Table/column names are the CIS §2 DDL verbatim: never
renamed here.

PostgREST has no cross-table transaction, so multi-write flows (resolve)
are best-effort sequences at the router level with logged partial-failure
warnings — see resolve_router.
"""

from typing import Optional

# Universe of fields written by this slice. The generated ids use the
# Postgres-side defaults (gen_random_uuid()); we rely on returning
# representation to read them back, which supabase-py does by default.
INVOICE_STATUS_DISPUTED = "DISPUTED_PENDING_IMS"


async def get_merchant(client, merchant_id: str) -> Optional[dict]:
    """Exact merchant lookup, or None."""
    if not merchant_id:
        return None
    response = await client.table("merchants").select("*").eq("id", merchant_id).limit(1).execute()
    rows = response.data or []
    return rows[0] if rows else None


async def first_merchant_with_invoice(client) -> Optional[dict]:
    """Fallback of last resort (B1 chain, step 3): the first seeded merchant
    that owns at least one invoice. Scoped to avoid guessing on zero-invoice
    stores; the table is small (30 merchants / 150 invoices)."""
    owners = await client.table("invoices").select("merchant_id").limit(150).execute()
    seen = []
    for row in owners.data or []:
        if row["merchant_id"] not in seen:
            seen.append(row["merchant_id"])
    for mid in seen:
        merchant = await get_merchant(client, mid)
        if merchant:
            return merchant
    return None


async def get_invoice_bundle(client, invoice_id: str) -> Optional[dict]:
    """Invoice + its supplier + its line items in one round trip.

    Shape: {..invoice columns.., suppliers: {...}|None, invoice_line_items: [..]}
    Line-item math is ALWAYS derived from invoice_line_items — the stored
    invoices.billed_total includes non-itemized charges (documented tension;
    see AGENTS.md). """
    response = (
        await client.table("invoices")
        .select("*, suppliers(name, gstin, phone), invoice_line_items(*)")
        .eq("id", invoice_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


async def get_loan_for_invoice(client, invoice_id: str) -> Optional[dict]:
    """Existing loan for an invoice, if the merchant already resolved it."""
    response = (
        await client.table("split_credit_loans").select("id, status").eq("invoice_id", invoice_id).limit(1).execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


async def get_ims_record_for_invoice(client, invoice_id: str) -> Optional[dict]:
    """The invoice's IMS record — every seeded invoice has exactly one, so
    resolve UPSERTS the dispute flag instead of blindly inserting a
    duplicate (upsert keeps the DoD invariant: exactly 1 IMS row per
    invoice)."""
    response = (
        await client.table("gst_ims_records").select("id, ims_status").eq("invoice_id", invoice_id).limit(1).execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


async def update_ims_status(client, record_id: str, ims_status: str) -> None:
    await client.table("gst_ims_records").update({"ims_status": ims_status}).eq("id", record_id).execute()


async def insert_loan(client, payload: dict) -> dict:
    response = await client.table("split_credit_loans").insert(payload).execute()
    return (response.data or [payload])[0]


async def insert_ims_record(client, payload: dict) -> dict:
    response = await client.table("gst_ims_records").insert(payload).execute()
    return (response.data or [payload])[0]


async def update_invoice_status(client, invoice_id: str, status: str) -> None:
    await client.table("invoices").update({"status": status}).eq("id", invoice_id).execute()
