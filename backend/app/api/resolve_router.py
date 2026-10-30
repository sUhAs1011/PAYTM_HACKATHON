"""POST /api/parcha/{id}/resolve — CIS §4 APPROVE_SPLIT persistence.

Resolve is REST-only under the user-approved policy: the current frontend
applies this response directly, so emitting PAYOUT_APPROVED as well would
double-apply the same transition. This is the documented CIS §4 Event 3
deviation; do not change without coordinating with Module 1.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.contracts import LoanSchedule, ResolveActionResponse, ResolveRequest, WhatsappClaim
from app.core import repo
from app.core.db import get_client
from app.core.money import as_float, dec, q2
from app.services.credit_rules import get_credit_rules

logger = logging.getLogger("parchapay.api")
router = APIRouter()

FALLBACK_DISTRIBUTOR_PHONE = "+919876543210"
SETTLEMENT_METHOD = "SOUNDBOX_7_DAY_SPLIT"


def _auto_locked_deadline(invoice_date: Optional[date]) -> Optional[str]:
    """Return the GST IMS 14th deadline for the invoice's applicable month."""
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
    if merchant is None:
        raise HTTPException(status_code=404, detail=f"merchant row for invoice {invoice_id} missing")

    existing = await repo.get_loan_for_invoice(client, invoice_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"invoice already resolved (loan {existing['id']})")
    if invoice.get("status") == "SETTLED":
        raise HTTPException(status_code=409, detail="invoice is SETTLED — nothing to resolve")

    principal = dec(invoice.get("approved_total", 0))
    if principal <= Decimal("0"):
        raise HTTPException(status_code=422, detail="invoice approved_total is not positive; nothing to finance")
    plan = await get_credit_rules().plan(merchant, principal, body.tenure_days)
    if not plan.is_eligible:
        raise HTTPException(
            status_code=409,
            detail="approved_total exceeds the 35% daily QR velocity cap for this tenure",
        )

    # PostgREST has no cross-table transaction. IMS is updated in place for
    # seeded invoices (one row per invoice); otherwise a pending row is added.
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
        await repo.insert_loan(
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
        status="SENT",  # queued-for-dispatch marker; live WhatsApp send is not implemented
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
