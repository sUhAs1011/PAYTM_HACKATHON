"""Shared API contracts (Module 2) — Pydantic mirror of contracts/contracts.ts.

Source of truth: Engineering Document Part 2 (CIS) §4/§5 and the golden
fixture `contracts/demo_bill_fixture.json`. Field names and casing are
IMMUTABLE — never rename, add, or drop fields to paper over gaps; flag
deltas instead (see the ASSUMPTION note below, which mirrors contracts.ts).

Vocabularies on purpose (map, never collapse):
  - invoice payload gst_ims_shield.status: SHIELD_* (audit vocabulary)
  - invoices.status: AUDITED | DISPUTED_PENDING_IMS | SETTLED
  - gst_ims_records.ims_status: PENDING | ACCEPTED | REJECTED
"""

from typing import List, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Audited invoice payload — CIS §4 Event 2 (AUDIT_COMPLETE.data) + §5 fixture
# ---------------------------------------------------------------------------


class ScanStartedData(BaseModel):
    session_id: str
    timestamp: str
    status: str
    message: str


class AuditedItem(BaseModel):
    item_name: str
    billed_qty: int
    printed_qty: int
    free_qty: int = 0
    billed_rate: float
    tax_percent: float
    true_landed_cost: float
    ocr_confidence: float  # 0.000–1.000; below 0.800 triggers yellow review
    has_pen_markup: bool = False
    # Open vocabulary — e.g. 'RATE_HIKE_AND_PEN_ERROR' | 'LOW_CONFIDENCE_REVIEW'
    discrepancy_type: str
    personal_history_rate: float
    mandi_pulse_median: float
    mandi_pulse_band: str
    # e.g. 'FLAGGED_HIGH' | 'OK'
    rate_status: str


class GstImsShield(BaseModel):
    status: str  # e.g. 'SHIELD_READY' (audit payload vocabulary)
    flag_reason: str
    deadline: str  # ISO date, e.g. '2026-11-14'


class SplitCreditPreApproval(BaseModel):
    is_eligible: bool
    max_credit_limit: float
    daily_deduction_amount: float
    tenure_days: int
    daily_velocity_cap: float
    autopay_mandate_registered: bool


class AuditCompleteData(BaseModel):
    # CIS delta (flagged, not papered over): the WS Event 2 example omits
    # supplier_gstin/invoice_date; REST responses add them (contracts.ts).
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
    # REST-only fields present in the golden fixture and CIS §4 REST responses.
    supplier_gstin: str
    invoice_date: str


# ---------------------------------------------------------------------------
# Resolve + payout — CIS §4
# ---------------------------------------------------------------------------


class ResolveRequest(BaseModel):
    # APPROVE_SPLIT is the ONLY resolve action in the spec. Do not add more.
    action: Literal["APPROVE_SPLIT"]
    tenure_days: int = Field(default=7, ge=1, le=30)


class WhatsappClaim(BaseModel):
    distributor_phone: str
    message_preview: str
    status: str  # e.g. 'SENT' (queued-for-dispatch marker in this slice)


class LoanSchedule(BaseModel):
    principal: float
    daily_deduction: float
    day_1_deducted: bool
    remaining_balance: float


class ResolveActionResponse(BaseModel):
    # ASSUMPTION (mirrors contracts.ts, needs cross-dev confirmation): CIS §4
    # names ResolveActionResponse but never defines its fields. This is
    # modelled on the PAYOUT_APPROVED.data payload — the documented outcome
    # of APPROVE_SPLIT.
    invoice_id: str
    settlement_method: str  # e.g. 'SOUNDBOX_7_DAY_SPLIT'
    whatsapp_claim: WhatsappClaim
    gst_ims_state: str  # invoices.status vocabulary, e.g. 'DISPUTED_PENDING_IMS'
    loan_schedule: LoanSchedule


# ---------------------------------------------------------------------------
# Demo + export — CIS §4
# ---------------------------------------------------------------------------


class LoadSampleRequest(BaseModel):
    sample_id: str  # e.g. 'sample_pen_edit_01'
