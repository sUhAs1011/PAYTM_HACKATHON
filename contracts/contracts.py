"""ParchaPay AI — Shared Pydantic contracts for FastAPI backend (Modules 2, 3, 4).

Source of truth: Engineering Document Part 2 — Core Interoperability
Specification (CIS) §3 (originally authored for Gemini 2.5 Flash) and §4 (REST + WebSocket).

IMMUTABLE: field names and casing mirror the CIS payloads and TypeScript contracts exactly.
"""

from typing import Any, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# CIS §3 structured vision contract; consumed by the Gemini 3.6 Flash runtime.
# ---------------------------------------------------------------------------

class BoundingBox2D(BaseModel):
    ymin: int = Field(..., ge=0, le=1000, description="Top-edge Y coordinate normalized to 0-1000")
    xmin: int = Field(..., ge=0, le=1000, description="Left-edge X coordinate normalized to 0-1000")
    ymax: int = Field(..., ge=0, le=1000, description="Bottom-edge Y coordinate normalized to 0-1000")
    xmax: int = Field(..., ge=0, le=1000, description="Right-edge X coordinate normalized to 0-1000")


class ExtractedLineItem(BaseModel):
    raw_item_name: str = Field(..., description="Verbatim item name or abbreviation from bill")
    billed_qty: int = Field(..., description="Billed quantity or handwritten adjusted quantity")
    printed_qty: int = Field(..., description="Original printed quantity before any handwritten pen edit")
    free_qty: int = Field(0, description="Free or promotional scheme units")
    unit_rate: float = Field(..., description="Billed wholesale rate before tax")
    gst_percent: float = Field(5.0, description="GST slab percentage (e.g., 0, 5, 12, 18)")
    line_total: float = Field(..., description="Printed or written line total")
    mrp: Optional[float] = Field(None, description="Printed retail MRP if present on bill")
    has_pen_markup: bool = Field(False, description="True if delivery pen strikethrough is present")
    pen_markup_box: Optional[BoundingBox2D] = Field(None, description="Bounding box around pen edit")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="OCR confidence for line item")


class RawExtractedInvoice(BaseModel):
    supplier_name: str = Field(..., description="Supplier or distributor business name")
    supplier_gstin: Optional[str] = Field(None, description="15-character GSTIN if printed")
    invoice_number: Optional[str] = Field(None, description="Invoice or Challan number")
    invoice_date: Optional[str] = Field(None, description="Date of the bill in YYYY-MM-DD")
    printed_grand_total: float = Field(..., description="Grand total printed or handwritten on bill")
    line_items: List[ExtractedLineItem] = Field(..., description="List of all extracted line items")


# ---------------------------------------------------------------------------
# CIS §4: REST & WebSocket Models (/ws/counter, /api/parcha/*)
# ---------------------------------------------------------------------------

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
    event: str
    data: Any


class ResolveRequest(BaseModel):
    action: str = "APPROVE_SPLIT"
    tenure_days: int = 7


class WhatsappClaimPreview(BaseModel):
    distributor_phone: str
    message_preview: str
    status: str = "SENT"


class LoanSchedule(BaseModel):
    principal: float
    daily_deduction: float
    day_1_deducted: bool
    remaining_balance: float


class PayoutApprovedData(BaseModel):
    invoice_id: str
    settlement_method: str = "SOUNDBOX_7_DAY_SPLIT"
    whatsapp_claim: WhatsappClaimPreview
    gst_ims_state: str = "DISPUTED_PENDING_IMS"
    loan_schedule: LoanSchedule


class ResolveActionResponse(PayoutApprovedData):
    pass


class LoadSampleRequest(BaseModel):
    sample_id: str = "sample_pen_edit_01"

