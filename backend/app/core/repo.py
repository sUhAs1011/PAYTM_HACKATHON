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
# Human-in-the-loop review layer (Module 3): drafts await the merchant's
# correction pass before the deterministic audit marks them verified.
INVOICE_STATUS_USER_PENDING_REVIEW = "user_pending_review"
INVOICE_STATUS_BILL_VERIFIED = "bill_verified"


async def get_merchant(client, merchant_id: str) -> Optional[dict]:
    """Exact merchant lookup, or None."""
    if not merchant_id:
        return None
    response = await client.table("merchants").select("*").eq("id", merchant_id).limit(1).execute()
    rows = response.data or []
    return rows[0] if rows else None


async def get_suppliers(client) -> list[dict]:
    response = await client.table("suppliers").select("id,name,gstin,phone,upi_vpa").limit(1000).execute()
    return response.data or []


async def get_canonical_skus(client) -> list[dict]:
    response = (
        await client.table("canonical_skus")
        .select("id,product_name,aliases,standard_mrp")
        .limit(1000)
        .execute()
    )
    return response.data or []


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


async def get_invoice_bundle(
    client,
    invoice_id: str,
    merchant_id: Optional[str] = None,
) -> Optional[dict]:
    """Invoice + its supplier + its line items in one round trip.

    Shape: {..invoice columns.., suppliers: {...}|None, invoice_line_items: [..]}
    Line-item math is ALWAYS derived from invoice_line_items — the stored
    invoices.billed_total includes non-itemized charges (documented tension;
    see AGENTS.md). """
    query = (
        client.table("invoices")
        .select("*, suppliers(name, gstin, phone), invoice_line_items(*)")
        .eq("id", invoice_id)
    )
    if merchant_id:
        query = query.eq("merchant_id", merchant_id)
    response = await query.limit(1).execute()
    rows = response.data or []
    return rows[0] if rows else None


async def get_pending_reviews(client, merchant_id: str) -> list[dict]:
    """All user_pending_review drafts for one merchant, items + supplier embedded."""
    response = (
        await client.table("invoices")
        .select("*, suppliers(name, gstin, phone), invoice_line_items(*)")
        .eq("merchant_id", merchant_id)
        .eq("status", INVOICE_STATUS_USER_PENDING_REVIEW)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


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


async def insert_invoice(client, payload: dict) -> dict:
    response = await client.table("invoices").insert(payload).execute()
    return (response.data or [payload])[0]


async def insert_invoice_line_items(client, payloads: list[dict]) -> list[dict]:
    if not payloads:
        return []
    response = await client.table("invoice_line_items").insert(payloads).execute()
    return response.data or payloads


async def insert_ims_record(client, payload: dict) -> dict:
    response = await client.table("gst_ims_records").insert(payload).execute()
    return (response.data or [payload])[0]


async def update_invoice_status(client, invoice_id: str, status: str) -> None:
    await client.table("invoices").update({"status": status}).eq("id", invoice_id).execute()


async def update_invoice(client, invoice_id: str, payload: dict) -> None:
    """General invoice update — used by the confirm-review flow to write
    corrected totals, status, and header fields in one call."""
    await client.table("invoices").update(payload).eq("id", invoice_id).execute()


async def update_invoice_line_item(client, item_id: str, payload: dict) -> None:
    """Apply merchant corrections plus recomputed audit fields to one
    persisted invoice_line_items row."""
    await client.table("invoice_line_items").update(payload).eq("id", item_id).execute()


async def delete_invoice(client, invoice_id: str) -> None:
    """Compensate for a failed multi-table scan insert; FK cascades remove children."""
    await client.table("invoices").delete().eq("id", invoice_id).execute()
