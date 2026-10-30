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
    "ExtractedLineItem",
    "GstImsShield",
    "LoadSampleRequest",
    "LoanSchedule",
    "PayoutApprovedData",
    "RawExtractedInvoice",
    "ResolveActionResponse",
    "ResolveRequest",
    "ScanStartedData",
    "SplitCreditPreApproval",
    "WhatsappClaim",
    "WhatsappClaimPreview",
    "WsEnvelope",
]
