"""Shared Pydantic contracts for ParchaPay AI Modules 2–4.

Source of truth: ED Part 2 CIS §3–§5 and `contracts/contracts.ts`.
Field names and casing are immutable. REST's `AuditedInvoiceResponse` is
wider than the CIS `AUDIT_COMPLETE` WebSocket payload by the documented
`supplier_gstin` / `invoice_date` fields.
"""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class BoundingBox2D(BaseModel):
    ymin: int = Field(..., ge=0, le=1000, description="Top-edge Y coordinate normalized to 0-1000")
    xmin: int = Field(..., ge=0, le=1000, description="Left-edge X coordinate normalized to 0-1000")
    ymax: int = Field(..., ge=0, le=1000, description="Bottom-edge Y coordinate normalized to 0-1000")
    xmax: int = Field(..., ge=0, le=1000, description="Right-edge X coordinate normalized to 0-1000")


class ExtractedLineItem(BaseModel):
    raw_item_name: str
    billed_qty: int
    printed_qty: int
    free_qty: int = 0
    unit_rate: float
    gst_percent: float = 5.0
    line_total: float
    mrp: Optional[float] = None
    has_pen_markup: bool = False
    pen_markup_box: Optional[BoundingBox2D] = None
    confidence_score: float = Field(..., ge=0.0, le=1.0)


class RawExtractedInvoice(BaseModel):
    supplier_name: str
    supplier_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    printed_grand_total: float
    line_items: List[ExtractedLineItem]


class AuditedItem(BaseModel):
    item_name: str
    billed_qty: int
    printed_qty: int
    free_qty: int
    billed_rate: float
    tax_percent: float
    true_landed_cost: float
    ocr_confidence: float
    has_pen_markup: bool
    discrepancy_type: str
    personal_history_rate: float
    mandi_pulse_median: float
    mandi_pulse_band: str
    rate_status: str


class GstImsShield(BaseModel):
    status: str
    flag_reason: str
    deadline: str


class SplitCreditPreApproval(BaseModel):
    is_eligible: bool
    max_credit_limit: float
    daily_deduction_amount: float
    tenure_days: int
    daily_velocity_cap: float
    autopay_mandate_registered: bool


class AuditCompleteData(BaseModel):
    invoice_id: str
    supplier_name: str
    invoice_number: str
    billed_total: float
    approved_total: float
    overcharge_amount: float
    audio_alert_url: str
    dispute_crop_url: str
    voice_transcript: str
    items: List[AuditedItem]
    gst_ims_shield: GstImsShield
    split_credit_pre_approval: SplitCreditPreApproval


class AuditedInvoiceResponse(AuditCompleteData):
    supplier_gstin: str
    invoice_date: str


# Human-in-the-loop review layer (Module 3 extension): scan persists the raw
# Gemini parse as a draft (invoices.status = 'user_pending_review'), the UI
# reviews/edits it, and the confirm POST runs the deterministic audit and
# flips status to 'bill_verified'. AUDIT_COMPLETE only fires after confirm.
class ScanDraftResponse(BaseModel):
    invoice_id: str
    merchant_id: str
    status: str
    supplier_name: str
    supplier_gstin: str
    invoice_number: str
    invoice_date: str
    billed_total: float
    item_count: int
    dispute_crop_url: str
    message: str = "Bill parsed - review the extracted items before confirming."


class DraftLineItem(BaseModel):
    id: str
    raw_item_name: str
    printed_qty: int
    billed_qty: int
    free_qty: int
    billed_rate: float
    tax_percent: float
    true_landed_cost: float
    mrp: Optional[float] = None
    ocr_confidence: float
    has_pen_markup: bool
    bounding_box: Optional[List[int]] = None
    canonical_sku_id: Optional[str] = None


class InvoiceDraftReview(BaseModel):
    invoice_id: str
    merchant_id: str
    supplier_id: Optional[str] = None
    supplier_name: str
    supplier_gstin: str
    invoice_number: str
    invoice_date: str
    billed_total: float
    status: str
    dispute_crop_url: str
    items: List[DraftLineItem]


class PendingReviewListResponse(BaseModel):
    merchant_id: str
    drafts: List[InvoiceDraftReview]


class LineItemCorrection(BaseModel):
    """Partial update to one persisted invoice_line_items row, addressed by id."""

    id: str
    raw_item_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    printed_qty: Optional[int] = Field(default=None, ge=0)
    billed_qty: Optional[int] = Field(default=None, ge=0)
    free_qty: Optional[int] = Field(default=None, ge=0)
    billed_rate: Optional[float] = Field(default=None, ge=0)
    tax_percent: Optional[float] = Field(default=None, ge=0, le=100)
    mrp: Optional[float] = Field(default=None, ge=0)


class ConfirmCorrectionsRequest(BaseModel):
    merchant_id: str
    invoice_number: Optional[str] = Field(default=None, min_length=1, max_length=100)
    invoice_date: Optional[str] = Field(default=None, min_length=1)
    billed_total: Optional[float] = Field(default=None, ge=0)
    corrections: List[LineItemCorrection] = Field(default_factory=list)


class ScanStartedData(BaseModel):
    session_id: str
    timestamp: str
    status: str
    message: str


class WsEnvelope(BaseModel):
    event: Literal["SCAN_STARTED", "AUDIT_COMPLETE", "PAYOUT_APPROVED"]
    data: Any


class ResolveRequest(BaseModel):
    action: Literal["APPROVE_SPLIT"]
    tenure_days: int = Field(default=7, ge=1, le=30)


class WhatsappClaim(BaseModel):
    distributor_phone: str
    message_preview: str
    status: str = "SENT"


# Backwards-compatible name used by Suhas's vision branch.
WhatsappClaimPreview = WhatsappClaim


class LoanSchedule(BaseModel):
    principal: float
    daily_deduction: float
    day_1_deducted: bool
    remaining_balance: float


class ResolveActionResponse(BaseModel):
    # CIS §4 names this response but does not define its fields; it follows
    # the documented PAYOUT_APPROVED.data shape in contracts/contracts.ts.
    invoice_id: str
    settlement_method: str = "SOUNDBOX_7_DAY_SPLIT"
    whatsapp_claim: WhatsappClaim
    gst_ims_state: str = "DISPUTED_PENDING_IMS"
    loan_schedule: LoanSchedule


PayoutApprovedData = ResolveActionResponse


class LoadSampleRequest(BaseModel):
    sample_id: str = "sample_pen_edit_01"


__all__ = [
    "AuditCompleteData",
    "AuditedInvoiceResponse",
    "AuditedItem",
    "BoundingBox2D",
    "ConfirmCorrectionsRequest",
    "DraftLineItem",
    "ExtractedLineItem",
    "GstImsShield",
    "InvoiceDraftReview",
    "LineItemCorrection",
    "LoadSampleRequest",
    "PendingReviewListResponse",
    "LoanSchedule",
    "PayoutApprovedData",
    "RawExtractedInvoice",
    "ResolveActionResponse",
    "ResolveRequest",
    "ScanDraftResponse",
    "ScanStartedData",
    "SplitCreditPreApproval",
    "WhatsappClaim",
    "WhatsappClaimPreview",
    "WsEnvelope",
]
