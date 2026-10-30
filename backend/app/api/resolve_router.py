"""Resolve Router (Paytm Button Trigger & Realtime Broadcast).

Endpoint:
- POST /api/parcha/{invoice_id}/resolve
"""

import logging
from fastapi import APIRouter

from app.api.scan_router import invoices_store
from app.contracts import (
    LoanSchedule,
    PayoutApprovedData,
    ResolveActionResponse,
    ResolveRequest,
    WhatsappClaimPreview,
)
from app.core.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/parcha", tags=["resolve"])


@router.post("/{invoice_id}/resolve", response_model=ResolveActionResponse)
async def resolve_parcha(invoice_id: str, body: ResolveRequest):
    """Handles 1-tap resolution approval when Paytm Button is pressed on /counter.

    Broadcasts PAYOUT_APPROVED event over WebSocket using dynamic values.
    """
    invoice = invoices_store.get(invoice_id)
    if invoice:
        principal = invoice.approved_total
        supplier = invoice.supplier_name
        inv_number = invoice.invoice_number
    else:
        principal = 13860.00
        supplier = "Sharmaji Wholesale Distributors"
        inv_number = "INV-2026-402"

    tenure = max(1, body.tenure_days)
    daily_deduction = round(principal / tenure, 2)
    remaining_balance = round(principal - daily_deduction, 2)

    payout_data = PayoutApprovedData(
        invoice_id=invoice_id,
        settlement_method="SOUNDBOX_7_DAY_SPLIT",
        whatsapp_claim=WhatsappClaimPreview(
            distributor_phone="+919876543210",
            message_preview=(
                f"Namaste {supplier}. Delivery received for Inv #{inv_number}. "
                f"Note: Delivery quantity pen-corrected. Approved amount: ₹{int(principal):,}. "
                "[View Verified Challan Crop & Collect via Paytm Link]"
            ),
            status="SENT",
        ),
        gst_ims_state="DISPUTED_PENDING_IMS",
        loan_schedule=LoanSchedule(
            principal=principal,
            daily_deduction=daily_deduction,
            day_1_deducted=True,
            remaining_balance=remaining_balance,
        ),
    )

    # Broadcast PAYOUT_APPROVED to all connected surfaces
    await ws_manager.broadcast("PAYOUT_APPROVED", payout_data.model_dump())

    return ResolveActionResponse(**payout_data.model_dump())
