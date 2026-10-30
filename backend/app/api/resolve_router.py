"""POST /api/parcha/{id}/resolve — CIS §4 (Module 2 slice 1).

Body: {"action": "APPROVE_SPLIT", "tenure_days": 7}. APPROVE_SPLIT is the
only action in the spec.

Behavior on a DB-backed invoice:
  1. Guards: unknown invoice → 404 · already-resolved (existing loan or
     status SETTLED) → 409 · approval≤0 → 422.
  2. Plan the schedule via the CreditRules seam (provisional Decimal
     formulas today; Module 4's engine replaces it without gateway
     changes).
  3. Best-effort write sequence (PostgREST has no cross-table tx):
     gst_ims_records row (PENDING) → split_credit_loans row → invoice
     status DISPUTED_PENDING_IMS. Any failure mid-sequence is logged with
     the stage name and returned as 500 so partial state is inspectable.
  4. Respond with ResolveActionResponse (PAYOUT_APPROVED.data shape — the
     documented ASSUMPTION in contracts.ts). WhatsApp dispatch stays a
     seam (log-only; live Business API is a later integration slice).

NOTE for the WebSocket slice (locked decision B2): scan broadcasts
SCAN_STARTED/AUDIT_COMPLETE, resolve broadcasts PAYOUT_APPROVED;
/api/demo/load-sample NEVER broadcasts.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.contracts import (
    LoanSchedule,
    ResolveActionResponse,
    ResolveRequest,
    WhatsappClaim,
)
from app.core import repo
from app.core.db import get_client
from app.core.money import as_float, dec, q2
from app.services.credit_rules import get_credit_rules

logger = logging.getLogger("parchapay.api")
router = APIRouter()

# The contract example's distributor phone: used only when the seeded
# supplier row has no phone (every seeded supplier does).
FALLBACK_DISTRIBUTOR_PHONE = "+919876543210"

SETTLEMENT_METHOD = "SOUNDBOX_7_DAY_SPLIT"


def _auto_locked_deadline(invoice_date: Optional[date]) -> Optional[str]:
    """The 14th of the invoice month, or of the month after it when the
    invoice is dated later than the 14th (fixture semantics: invoice
    2026-10-30 → deadline 2026-11-14)."""
    if invoice_date is None:
        return None
    if invoice_date.day <= 14:
        return date(invoice_date.year, invoice_date.month, 14).isoformat()
    if invoice_date.month == 12:
        return date(invoice_date.year + 1, 1, 14).isoformat()
    return date(invoice_date.year, invoice_date.month + 1, 14).isoformat()


@router.post("/api/parcha/{invoice_id}/resolve", response_model=ResolveActionResponse)
async def resolve_parcha(invoice_id: str, body: ResolveRequest) -> ResolveActionResponse:
    client = await get_client()

    bundle = await repo.get_invoice_bundle(client, invoice_id)
    if not bundle:
        raise HTTPException(status_code=404, detail=f"invoice {invoice_id} not found")
    invoice = bundle
    supplier = bundle.get("suppliers") or None
    merchant = await repo.get_merchant(client, bundle.get("merchant_id", ""))
    if merchant is None:  # FK-guaranteed; defensive only
        raise HTTPException(status_code=404, detail=f"merchant row for invoice {invoice_id} missing")

    existing = await repo.get_loan_for_invoice(client, invoice_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"invoice already resolved (loan {existing['id']})")
    if invoice.get("status") == "SETTLED":
        raise HTTPException(status_code=409, detail="invoice is SETTLED — nothing to resolve")

    principal = dec(invoice.get("approved_total", 0))
    if principal <= Decimal("0"):
        raise HTTPException(status_code=422, detail="invoice approved_total is not positive; nothing to finance")

    plan = get_credit_rules().plan(merchant, principal, body.tenure_days)

    # --- best-effort write sequence (no cross-table tx in PostgREST) ---
    # IMS: every invoice already carries an IMS record in the seeded data,
    # so resolve upserts the dispute flag (PENDING = disputed/pending
    # re-verification in ims vocabulary) rather than duplicating the row.
    try:
        ims = await repo.get_ims_record_for_invoice(client, invoice_id)
        if ims:
            await repo.update_ims_status(client, ims["id"], "PENDING")
        else:
            await repo.insert_ims_record(
                client,
                {
                    "invoice_id": invoice_id,
                    "gstin_supplier": (supplier or {}).get("gstin"),
                    "invoice_number": invoice.get("invoice_number"),
                    "ims_status": "PENDING",
                    "auto_locked_deadline": _auto_locked_deadline(invoice.get("invoice_date")),
                },
            )
    except Exception as exc:
        raise _write_failure("gst_ims_records upsert", exc) from exc

    try:
        loan = await repo.insert_loan(
            client,
            {
                "invoice_id": invoice_id,
                "merchant_id": merchant["id"],
                "principal_amount": str(q2(plan.principal)),
                "daily_deduction_rate": str(plan.daily_deduction),
                "tenure_days": body.tenure_days,
                "daily_cap_limit": str(plan.daily_cap),
                "autopay_mandate_active": True,
                "remaining_balance": str(plan.remaining_balance),
                "status": "ACTIVE",
            },
        )
    except Exception as exc:
        raise _write_failure("split_credit_loans insert", exc) from exc

    try:
        await repo.update_invoice_status(client, invoice_id, repo.INVOICE_STATUS_DISPUTED)
    except Exception as exc:
        raise _write_failure("invoices.status update", exc) from exc

    claim = WhatsappClaim(
        distributor_phone=(supplier or {}).get("phone") or FALLBACK_DISTRIBUTOR_PHONE,
        message_preview=(
            f"Namaste {(supplier or {}).get('name') or 'Supplier'}. "
            f"Delivery received for Inv #{invoice.get('invoice_number') or invoice_id}. "
            f"Amount approved: Rs {as_float(plan.principal)}. "
            f"Day 1: {as_float(plan.daily_deduction)} deducted from today's QR sweep. "
            "[View Verified Challan Crop & Collect via Paytm Link]"
        ),
        status="SENT",  # queued-for-dispatch marker; live send is a later slice
    )
    return ResolveActionResponse(
        invoice_id=invoice_id,
        settlement_method=SETTLEMENT_METHOD,
        whatsapp_claim=claim,
        gst_ims_state=repo.INVOICE_STATUS_DISPUTED,
        loan_schedule=LoanSchedule(
            principal=as_float(plan.principal),
            daily_deduction=as_float(plan.daily_deduction),
            day_1_deducted=True,
            remaining_balance=as_float(plan.remaining_balance),
        ),
    )


def _write_failure(stage: str, exc: Exception) -> HTTPException:
    logger.error("resolve write sequence failed at %s: %s", stage, exc)
    return HTTPException(status_code=500, detail=f"resolve failed at {stage}; partial state inspectable in logs")
