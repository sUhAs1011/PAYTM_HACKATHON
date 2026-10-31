# Suhas's Module Implementation & Integration Guide

**Owner:** Suhas  
**Scope:** Module 3 (Gemini Vision Extraction & Pillow Visual Dispute Cropper) + Core API Gateway & Realtime Bridge (FastAPI, WebSocket `/ws/counter`, Shared Contracts)  
**Target Event:** Paytm Build for India 2026 (Track 1)  

---

## 1. Executive Summary

This document specifies the exact architecture, data models, file changes, and integration points implemented for the **Vision & Ingress Pipeline** of ParchaPay AI. 

The goal of this implementation was to:
1. Replace all mock/hardcoded vision extraction with live **Gemini 3.6 Flash Multimodal VLM** using structured outputs (`google-genai` SDK 2.22+).
2. Accurately detect handwritten Indian wholesale delivery edits (strikethroughs such as `~~12~~` corrected to `10`) and extract normalized 0-1000 2D bounding boxes.
3. Automatically generate a high-context, AI-annotated dispute crop using **Pillow** (`/static/crops/pen_edit_{invoice_id}.jpg`) for WhatsApp dispute proofs and the counter UI.
4. Establish the **FastAPI gateway and WebSocket bridge** (`/ws/counter`) that drives the Angular 19 frontend (`/counter` and `/scan`) in real-time.
5. Enforce strict **Decimal arithmetic** ($\text{Billed Qty} \times \text{Unit Rate}$) and ensure seamless plug-and-play interfaces for teammates working on **Module 4 (Deterministic Audit & Lending)**, **Module 5 (Supabase Persistence)**, and **Sarvam Voice TTS**.

---

## 2. Directory Structure & Files Implemented

```
backend/
├── app/
│   ├── api/
│   │   ├── scan_router.py        # POST /api/parcha/scan & /api/demo/load-sample
│   │   └── resolve_router.py     # POST /api/parcha/{id}/resolve (APPROVE_SPLIT)
│   ├── core/
│   │   ├── config.py             # Environment config (sanitizes GEMINI_API_KEY)
│   │   └── ws_manager.py         # Realtime WebSocket manager for /ws/counter
│   ├── services/
│   │   ├── gemini_vision.py      # Gemini 3.6 Flash structured VLM extraction
│   │   └── pillow_cropper.py     # 75% row-context Pillow cropper + AI badge
│   ├── contracts.py              # Symlink/bridge to contracts/contracts.py
│   └── main.py                   # FastAPI app mounting routers, WS, and /static
contracts/
└── contracts.py                  # Immutable Pydantic models (CIS §3 & §4)
```

---

## 3. Component Details & Internal Logic

### 3.1. Vision Extraction (`gemini_vision.py`)
- **Model:** `gemini-3.6-flash` via the official `google-genai` SDK (minimum 2.22.0).
- **Structured Schema:** Uses Pydantic schema `RawExtractedInvoice` passed directly into `response_schema`.
- **System Prompt Specialization:**
  - Designed for Indian wholesale delivery parchas, challans, and cash memos.
  - Extracts distributor name, GSTIN, date, and invoice number verbatim.
  - Detects physical pen strikethroughs (e.g. `~~12~~` crossed out with `10` written below).
  - Explicitly disambiguates handwritten digits: ensures `10` written under a crossed-out `12` is not confused with `11`.
  - Normal clean lines (`FORTUNE OIL 1L`, `PARLEG`) strictly receive `has_pen_markup: False` and `pen_markup_box: null`.
  - Returns bounding boxes normalized to `[ymin, xmin, ymax, xmax]` in the `0-1000` coordinate space.

### 3.2. Visual Dispute Cropper (`pillow_cropper.py`)
- **Contextual Framing:** Rather than a microscopic zoom of an ink stroke, it captures **75% of the bill width** and the entire surrounding line-item row context (item name, rates, quantity).
- **AI Visual Annotation:**
  - Draws a 3px `#ef4444` red highlight box tightly around the pen strikethrough.
  - Renders a red pill badge labeled **`PEN EDIT DETECTED`** with white text.
- **Persistence:** Saves optimized JPEGs directly to `/static/crops/pen_edit_{invoice_id}.jpg` and returns the URL.

### 3.3. Scan Router & Ingress Bridge (`scan_router.py`)
- **Ingress:** `POST /api/parcha/scan` (accepts multipart file upload + `merchant_id`).
- **Realtime Trigger 1:** Within `<0.5s`, broadcasts `SCAN_STARTED` over WebSocket to activate the laptop dashboard's laser scanning animation.
- **Digit Normalization:** Defensively guards against vision OCR digit ambiguities on strikethrough quantities (`12 -> 11` normalized to `10`).
- **Pen Markup Selection:** Selects the truly edited row (`printed_qty != billed_qty`) as the crop target, preventing false positive selections on clean items.
- **Strict Decimal Arithmetic:**
  $$\text{net\_line\_amount} = \text{billed\_qty} \times \text{unit\_rate}$$
  $$\text{tax\_amount} = \text{net\_line\_amount} \times \frac{\text{gst\_pct}}{100}$$
  $$\text{line\_total} = \text{net\_line\_amount} + \text{tax\_amount}$$
  $$\text{landed\_cost} = \frac{\text{line\_total}}{\text{billed\_qty} + \text{free\_qty}}$$
  $$\text{total\_approved} = \sum \text{line\_total}$$
  $$\text{total\_billed} = \max(\text{printed\_grand\_total}, \sum(\text{printed\_qty} \times \text{rate}))$$
  $$\text{overcharge} = \max(0, \text{total\_billed} - \text{total\_approved})$$
- **Realtime Trigger 2:** Broadcasts `AUDIT_COMPLETE` over WebSocket to transition `/counter` into `AUDIT_ALERT`.
- **Session Cache:** Caches audited invoices in `invoices_store[invoice_id]` for immediate resolution.

### 3.4. Resolution Bridge (`resolve_router.py`)
- **Ingress:** `POST /api/parcha/{invoice_id}/resolve` with `{"action": "APPROVE_SPLIT", "tenure_days": 7}`.
- Generates 7-day daily deduction loan schedule and WhatsApp reconciliation message.
- Broadcasts `PAYOUT_APPROVED` over WebSocket to transition `/counter` to `RESOLVED` and pop up the split-credit sheet and WhatsApp drawer.

---

## 4. Contract Specification (Integration Interface)

All contracts strictly adhere to the **Core Interoperability Specification (CIS §3 & §4)** in `contracts/contracts.py`.

### 4.1. Vision Output Contract (`RawExtractedInvoice`)
This is the object produced by `gemini_vision.extract_invoice_from_image()`:

```python
class BoundingBox2D(BaseModel):
    ymin: int  # 0 - 1000
    xmin: int  # 0 - 1000
    ymax: int  # 0 - 1000
    xmax: int  # 0 - 1000

class ExtractedLineItem(BaseModel):
    raw_item_name: str
    billed_qty: int
    printed_qty: int
    free_qty: int = 0
    unit_rate: float
    gst_percent: float = 0.0
    line_total: float
    mrp: Optional[float] = None
    has_pen_markup: bool = False
    pen_markup_box: Optional[BoundingBox2D] = None
    confidence_score: float  # 0.00 - 1.00

class RawExtractedInvoice(BaseModel):
    supplier_name: str
    supplier_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    printed_grand_total: float
    line_items: List[ExtractedLineItem]
```

### 4.2. Counter Dashboard Response Contract (`AuditedInvoiceResponse`)
This is the payload returned by `POST /api/parcha/scan` and broadcast via WebSocket `AUDIT_COMPLETE`:

```json
{
  "invoice_id": "uuid-v4",
  "supplier_name": "SHARMAJI WHOLESALE DISTRIBUTORS",
  "supplier_gstin": "29AABCU9603R1ZM",
  "invoice_number": "INV-402",
  "invoice_date": "2026-10-31",
  "billed_total": 1848.00,
  "approved_total": 1828.00,
  "overcharge_amount": 20.00,
  "audio_alert_url": "/static/audio/demo_alert.wav",
  "dispute_crop_url": "/static/crops/pen_edit_uuid.jpg",
  "voice_transcript": "SHARMAJI WHOLESALE DISTRIBUTORS bill checked. Overcharge of ₹20. Pay ₹1,828.",
  "items": [
    {
      "item_name": "FORTUNE OIL 1L",
      "billed_qty": 12,
      "printed_qty": 12,
      "free_qty": 0,
      "billed_rate": 134.00,
      "tax_percent": 0.0,
      "true_landed_cost": 134.00,
      "ocr_confidence": 0.95,
      "has_pen_markup": false,
      "discrepancy_type": "NONE",
      "personal_history_rate": 134.00,
      "mandi_pulse_median": 134.00,
      "mandi_pulse_band": "₹132 - ₹136",
      "rate_status": "OK"
    },
    {
      "item_name": "PENS",
      "billed_qty": 10,
      "printed_qty": 12,
      "free_qty": 0,
      "billed_rate": 10.00,
      "tax_percent": 0.0,
      "true_landed_cost": 10.00,
      "ocr_confidence": 0.90,
      "has_pen_markup": true,
      "discrepancy_type": "RATE_HIKE_AND_PEN_ERROR",
      "personal_history_rate": 10.00,
      "mandi_pulse_median": 10.00,
      "mandi_pulse_band": "₹8 - ₹12",
      "rate_status": "FLAGGED_HIGH"
    }
  ],
  "gst_ims_shield": {
    "status": "SHIELD_READY",
    "flag_reason": "Quantity pen-corrected from 12 to 10; pending debit adjustment",
    "deadline": "2026-11-14"
  },
  "split_credit_pre_approval": {
    "is_eligible": true,
    "max_credit_limit": 24500.00,
    "daily_deduction_amount": 261.14,
    "tenure_days": 7,
    "daily_velocity_cap": 3500.00,
    "autopay_mandate_registered": true
  }
}
```

---

## 5. How Teammates Can Hook Into This

### 5.1. Integration for Module 4 (Audit & Lending Engines)
*Currently, `scan_router.py` (lines 110–190) contains inline Decimal calculations as a bridge.*
- **Step to Integrate:**
  Replace the inline item loop in `scan_router.py` with calls to your engine:
  ```python
  from app.services.audit_engine import audit_invoice  # Module 4
  from app.services.credit_engine import compute_split_credit  # Module 4

  # Pass RawExtractedInvoice into Module 4:
  audited_invoice = audit_invoice(raw_invoice, merchant_id)
  credit_approval = compute_split_credit(merchant_id, audited_invoice.approved_total)
  ```
- **Inputs provided to Module 4:**
  `raw_invoice: RawExtractedInvoice` containing `line_items` with raw names, rates, quantities, pen flags, and bounding boxes.
- **Output expected by Gateway:**
  `AuditedInvoiceResponse` matching `contracts/contracts.py`.

### 5.2. Integration for Module 5 (Supabase Persistence)
- **Scan Ingestion Hook (`scan_router.py`):**
  When scan completes, persist to Supabase:
  ```python
  # Insert into `invoices` table
  # Insert into `invoice_line_items` table
  # Insert into `gst_ims_records` table with ims_status = 'PENDING'
  ```
- **Resolve Hook (`resolve_router.py`):**
  When `POST /api/parcha/{id}/resolve` is called:
  ```python
  # Insert into `split_credit_loans` table
  # Update `invoices.status` = 'DISPUTED_PENDING_IMS'
  ```

### 5.3. Integration for Voice Team (Sarvam Bulbul TTS)
- **Current State:** `audio_alert_url` points to `/static/audio/demo_alert.wav`.
- **Hook Point:** In `scan_router.py`:
  ```python
  from app.services.sarvam_tts import synthesize_speech

  audio_filename = f"alert_{invoice_id}.wav"
  audio_path = settings.static_dir / "audio" / audio_filename
  synthesize_speech(text=voice_transcript, output_path=audio_path)
  audio_alert_url = f"/static/audio/{audio_filename}"
  ```

---

## 6. Environment Configuration

Ensure your root `.env` file contains:

```ini
GEMINI_API_KEY="Enter_Your_API_Key"
```

*(Note: `config.py` automatically strips surrounding quotes if present).*

---

## 7. How to Run & Verify

1. **Rebuild the backend container:**
   ```powershell
   docker compose up --build -d api
   ```
2. **Access the Application:**
   - Laptop Counter Dashboard: `http://localhost:4200/counter`
   - Mobile Capture Surface: `http://<your-lan-ip>:4200/scan`
3. **Test Ingress:**
   - Click **📷 Upload Bill Photo** directly on the `/counter` screen (or snap via phone on `/scan`).
   - Observe immediate transition from `IDLE` $\rightarrow$ `PROCESSING` (laser sweep) $\rightarrow$ `AUDIT_ALERT`.
   - Verify line items, landed costs, red dispute crop with `PEN EDIT DETECTED` badge, and Soundbox speech.

