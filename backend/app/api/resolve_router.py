"""POST /api/parcha/{id}/resolve — CIS §4 APPROVE_SPLIT persistence.

Resolve is REST-only under the user-approved policy: the current frontend
applies this response directly, so emitting PAYOUT_APPROVED as well would
double-apply the same transition. This is the documented CIS §4 Event 3
deviation; do not change without coordinating with Module 1.
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from app.contracts import LoanSchedule, ResolveActionResponse, ResolveRequest, WhatsappClaim
from app.core import repo
from app.core.db import get_client
from app.core.demo_auth import require_demo_auth
from app.core.money import as_float, dec, q2
from app.services.pipeline import FixturePipeline
from app.services.credit_rules import get_credit_rules
from app.credit.db.query import create_ledger_entry, get_loan_ledger

logger = logging.getLogger("parchapay.api")
router = APIRouter()

FALLBACK_DISTRIBUTOR_PHONE = "+919876543210"
SETTLEMENT_METHOD = "SOUNDBOX_7_DAY_SPLIT"
IST = ZoneInfo("Asia/Kolkata")
DEMO_FIXTURE_INVOICE_ID = "demo-golden-fixture-001"
_demo_fixture_cache = FixturePipeline()


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
async def resolve_parcha(
    invoice_id: str,
    body: ResolveRequest,
    _demo_auth: None = Depends(require_demo_auth),
) -> ResolveActionResponse:
    # The golden fixture has no persisted invoice/merchant row. Preserve its
    # demo Paytm Button flow with a REST-only simulation and no DB/ledger writes.
    if invoice_id == DEMO_FIXTURE_INVOICE_ID:
        fixture = _demo_fixture_cache.load()
        pre_approval = fixture.split_credit_pre_approval
        if body.tenure_days != pre_approval.tenure_days:
            raise HTTPException(
                status_code=422,
                detail=f"demo fixture supports {pre_approval.tenure_days}-day split only",
            )
        principal = dec(fixture.approved_total)
        daily_deduction = dec(pre_approval.daily_deduction_amount)
        return ResolveActionResponse(
            invoice_id=invoice_id,
            settlement_method=SETTLEMENT_METHOD,
            whatsapp_claim=WhatsappClaim(
                distributor_phone=FALLBACK_DISTRIBUTOR_PHONE,
                message_preview=(
                    f"Namaste {fixture.supplier_name}. Delivery received for Inv #{fixture.invoice_number}. "
                    f"Demo fixture amount approved: Rs {as_float(principal)}. "
                    f"Day 1 simulated deduction: Rs {as_float(daily_deduction)}. "
                    "[View Verified Challan Crop & Collect via Paytm Link]"
                ),
                status="SENT",
            ),
            gst_ims_state=repo.INVOICE_STATUS_DISPUTED,
            loan_schedule=LoanSchedule(
                principal=as_float(principal),
                daily_deduction=as_float(daily_deduction),
                day_1_deducted=True,
                remaining_balance=as_float(q2(principal - daily_deduction)),
            ),
        )

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
    if invoice.get("status") == repo.INVOICE_STATUS_USER_PENDING_REVIEW:
        raise HTTPException(status_code=409, detail="invoice is awaiting merchant review — confirm first")
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

    loan = None
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
        await _write_day_one_ledger(client, loan, merchant["id"], plan.daily_deduction)
    except Exception as exc:
        raise _write_failure("merchant_account_ledger Day-1 LOAN_DEDUCT", exc) from exc

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


async def _write_day_one_ledger(client, loan: dict, merchant_id: str, deduction: Decimal) -> None:
    """Record the Day-1 deduction already represented in remaining_balance.

    The unique (loan, IST-day) index makes this ledger row idempotent. If the
    insert response fails ambiguously, inspect the row before compensating the
    new loan so a committed debit is never paired with a deleted loan.
    """
    loan_id = loan.get("id")
    if not loan_id:
        raise RuntimeError("loan insert returned no ID for the Day-1 ledger entry")
    amount = q2(-deduction)
    entry_ts = datetime.now(timezone.utc)
    payload = {
        "merchant_id": merchant_id,
        "loan_id": loan_id,
        "kind": "LOAN_DEDUCT",
        "amount": str(amount),
        "entry_ts": entry_ts.isoformat(),
    }
    try:
        await create_ledger_entry(payload)
        return
    except Exception:
        logger.exception("Day-1 ledger insert failed; checking for committed entry loan_id=%s", loan_id)

    try:
        rows = await get_loan_ledger(loan_id)
    except Exception:
        logger.exception("could not verify Day-1 ledger insert; preserving loan_id=%s", loan_id)
        raise RuntimeError("Day-1 ledger insert outcome is unknown; loan preserved for inspection")

    target_day = entry_ts.astimezone(IST).date()
    for row in rows:
        raw_ts = row.get("entry_ts")
        if not raw_ts:
            continue
        row_ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        if row_ts.tzinfo is None:
            row_ts = row_ts.replace(tzinfo=timezone.utc)
        if (
            row_ts.astimezone(IST).date() == target_day
            and row.get("kind") == "LOAN_DEDUCT"
            and q2(dec(row.get("amount", 0))) == amount
        ):
            return

    if rows:
        raise RuntimeError("loan already has a different ledger event for the Day-1 IST date")
    try:
        await repo.delete_loan(client, str(loan_id))
    except Exception as exc:
        logger.exception("failed to compensate loan after Day-1 ledger insert failure loan_id=%s", loan_id)
        raise RuntimeError("Day-1 ledger insert failed and loan compensation failed") from exc
    raise RuntimeError("Day-1 ledger insert failed; newly created loan was removed")
