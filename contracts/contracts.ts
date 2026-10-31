/**
 * ParchaPay AI — Shared TypeScript contracts for the Angular client (Module 1).
 *
 * Source of truth: Engineering Document Part 2 — Core Interoperability
 * Specification (CIS) §4 (REST + WebSocket) and §5 (golden fixture).
 *
 * IMMUTABLE: field names and casing below mirror the CIS payloads exactly.
 * Do not rename, add, or drop fields to paper over gaps — flag them instead.
 */

// ---------------------------------------------------------------------------
// WebSocket envelopes (/ws/counter) — CIS §4
// ---------------------------------------------------------------------------

export type WsEventName = 'SCAN_STARTED' | 'AUDIT_COMPLETE' | 'PAYOUT_APPROVED';

export interface WsEnvelope<TData = unknown> {
  event: WsEventName;
  data: TData;
}

/** CIS §4 — Event 1: SCAN_STARTED data */
export interface ScanStartedData {
  session_id: string;
  timestamp: string;
  status: string; // e.g. 'PROCESSING_IMAGE'
  message: string;
}

// ---------------------------------------------------------------------------
// Audited invoice payload — CIS §4 Event 2 (AUDIT_COMPLETE.data) + §5 fixture
// ---------------------------------------------------------------------------

export interface AuditedItem {
  item_name: string;
  billed_qty: number;
  printed_qty: number;
  free_qty: number;
  billed_rate: number;
  tax_percent: number;
  true_landed_cost: number;
  ocr_confidence: number; // 0.000–1.000; below 0.800 triggers yellow review
  has_pen_markup: boolean;
  /** Open vocabulary — e.g. 'RATE_HIKE_AND_PEN_ERROR' | 'LOW_CONFIDENCE_REVIEW' */
  discrepancy_type: string;
  personal_history_rate: number;
  mandi_pulse_median: number;
  mandi_pulse_band: string;
  /** e.g. 'FLAGGED_HIGH' | 'OK' */
  rate_status: string;
}

export interface GstImsShield {
  /** e.g. 'SHIELD_READY' (audit payload vocabulary) */
  status: string;
  flag_reason: string;
  /** ISO date, e.g. '2026-11-14' */
  deadline: string;
}

export interface SplitCreditPreApproval {
  is_eligible: boolean;
  max_credit_limit: number;
  daily_deduction_amount: number;
  tenure_days: number;
  daily_velocity_cap: number;
  autopay_mandate_registered: boolean;
}

/**
 * AUDIT_COMPLETE.data — CIS §4 Event 2 payload.
 *
 * CIS delta (flagged, not papered over): the Event 2 example omits
 * `supplier_gstin` and `invoice_date`, while the golden fixture (§5) and the
 * REST responses (`/api/parcha/scan`, `/api/demo/load-sample`) include them.
 * The WS shape is therefore the narrower type; REST responses use
 * `AuditedInvoiceResponse`.
 */
export interface AuditCompleteData {
  invoice_id: string;
  supplier_name: string;
  invoice_number: string;
  billed_total: number;
  approved_total: number;
  overcharge_amount: number;
  audio_alert_url: string;
  dispute_crop_url: string;
  voice_transcript: string;
  items: AuditedItem[];
  gst_ims_shield: GstImsShield;
  split_credit_pre_approval: SplitCreditPreApproval;
}

/** Response of POST /api/parcha/scan and POST /api/demo/load-sample — CIS §4 + §5 */
export interface AuditedInvoiceResponse extends AuditCompleteData {
  supplier_gstin: string;
  invoice_date: string;
}

// ---------------------------------------------------------------------------
// Resolve + payout — CIS §4
// ---------------------------------------------------------------------------

/** POST /api/parcha/{id}/resolve request body. APPROVE_SPLIT is the only action in the spec. */
export interface ResolveRequest {
  action: 'APPROVE_SPLIT';
  tenure_days: number;
}

export interface WhatsappClaim {
  distributor_phone: string;
  message_preview: string;
  /** e.g. 'SENT' */
  status: string;
}

export interface LoanSchedule {
  principal: number;
  daily_deduction: number;
  day_1_deducted: boolean;
  remaining_balance: number;
}

/**
 * ASSUMPTION — CIS §4 names `ResolveActionResponse` but never defines its
 * fields. This type is modelled on the PAYOUT_APPROVED.data payload, the
 * documented outcome of APPROVE_SPLIT. CONFIRM WITH DEV 2 (Module 2) before
 * locking. `gst_ims_state` uses the invoices.status vocabulary
 * ('DISPUTED_PENDING_IMS'), not gst_ims_records.ims_status — mapped, never collapsed.
 */
export interface ResolveActionResponse {
  invoice_id: string;
  /** e.g. 'SOUNDBOX_7_DAY_SPLIT' */
  settlement_method: string;
  whatsapp_claim: WhatsappClaim;
  /** e.g. 'DISPUTED_PENDING_IMS' (invoices.status vocabulary) */
  gst_ims_state: string;
  loan_schedule: LoanSchedule;
}

/** CIS §4 — Event 3: PAYOUT_APPROVED data (same shape as the resolve response). */
export type PayoutApprovedData = ResolveActionResponse;

// ---------------------------------------------------------------------------
// Demo fallback + export — CIS §4
// ---------------------------------------------------------------------------

export interface LoadSampleRequest {
  /** e.g. 'sample_pen_edit_01' */
  sample_id: string;
}

export type ExportFormat = 'tally' | 'marg';

/* ── Opt-in human review mode (additive, not CIS) ────────────────────── */

export interface DraftLineItem {
  id: string;
  raw_item_name: string;
  printed_qty: number;
  billed_qty: number;
  free_qty: number;
  billed_rate: number;
  tax_percent: number;
  true_landed_cost?: number;
  mrp?: number | null;
  ocr_confidence: number;
  has_pen_markup: boolean;
  bounding_box?: number[] | null;
  canonical_sku_id?: string | null;
}

export interface ScanDraftResponse {
  invoice_id: string;
  merchant_id: string;
  supplier_name: string;
  supplier_gstin: string;
  invoice_number: string;
  invoice_date: string;
  billed_total: number;
  status: string;
  dispute_crop_url: string;
  items: DraftLineItem[];
}

export interface InvoiceDraftReview extends ScanDraftResponse {
  supplier_id?: string | null;
}

export interface PendingReviewListResponse {
  merchant_id: string;
  drafts: InvoiceDraftReview[];
}

export interface LineItemCorrection {
  id: string;
  raw_item_name?: string;
  printed_qty?: number;
  billed_qty?: number;
  free_qty?: number;
  billed_rate?: number;
  tax_percent?: number;
}

export interface ConfirmCorrectionsRequest {
  merchant_id: string;
  corrections: LineItemCorrection[];
}

