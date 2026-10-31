# ParchaPay AI — Demo Setup & Architecture Quick Reference

This reference guide contains everything needed to configure, run, and demonstrate the ParchaPay AI dual-surface setup across a laptop (countertop display) and a smartphone (mobile scanner).

---

## 1. Local Network Configuration (Phone + Laptop)

> **Venue / Hackathon Wi-Fi Warning:** Most commercial and hotel Wi-Fi networks enable **Client (AP) Isolation**, which prevents devices on the same Wi-Fi from reaching each other. For a foolproof demo, use your phone's personal hotspot.

### Step-by-Step Connection
1. **Enable Phone Hotspot:** Turn on the Personal Hotspot on your smartphone and connect your laptop to it (or ensure both devices are on the same unisolated Wi-Fi network).
2. **Find Your Laptop's Local IPv4 Address:**
   * Open PowerShell / Command Prompt on Windows:
     ```powershell
     ipconfig
     ```
   * Find the active adapter (e.g. *Wireless LAN adapter Wi-Fi*) and note the `IPv4 Address` (e.g. `192.168.43.120`).
3. **Verify Port Accessibility:**
   * Angular dev server inside Docker listens on `0.0.0.0:4200` and is exposed to the host.
   * If prompted by Windows Defender Firewall, allow incoming connections on port `4200`.

---

## 2. Screen URLs to Open

| Device | Role | URL | Notes |
| :--- | :--- | :--- | :--- |
| **Laptop** (Projector display) | **Paytm Soundbox Digital Twin & Audit Ledger** | `http://localhost:4200/counter` | Desktop-optimized (widescreen). Keep open on laptop screen. |
| **Phone** | **Mobile Parchas Scanner** | `http://<LAPTOP_IP>:4200/scan`<br>*(e.g. `http://192.168.43.120:4200/scan`)* | Mobile-optimized (portrait). Launches native phone camera app. |

> `/scan` uses a hidden HTML5 file input with `capture="environment"` and `accept="image/*"`. This natively launches the phone's rear camera without requiring HTTPS or WebRTC `getUserMedia`.

---

## 3. End-to-End Demo Workflow (4 Journey States)

```
[Phone: /scan or laptop Upload Bill] [Laptop Projector: /counter]
      │                                     ▲
      │ (POST image)                        │ (WebSocket /ws/counter)
      ▼                                     │
[FastAPI Gateway] ──► [WebSocket Broadcast: SCAN_STARTED (<0.5s)]
      │
      ├──► [Gemini 2.5 Flash VLM] ──► Pillow Cropper ──► /static/crops/
      │          │ (Raw JSON + Bounding Boxes)
      │          ▼
      ├──► [Deterministic Python Engine (Decimal)]
      │          │ • Checksums & True Landed Unit Cost
      │          │ • 3-Tier Waterfall (History -> Mandi-Pulse -> MRP Floor)
      │          │ • 7-Day Split-Credit (35% Velocity Cap)
      │          ▼
      └──► [Supabase Postgres + pgvector]
                 │
                 ▼
       [Broadcast: AUDIT_COMPLETE (<3.5s)] ──► [Soundbox Speaks & Displays Card]
                 │
                 ▼
        [Merchant Clicks Paytm Button] ───────► [POST /resolve response]
                                                • WhatsApp Dispute Preview
                                                • GST IMS Shield Active
                                                • 7-Day QR Split Schedule
```

**Current integration notes:** uploaded scans use Gemini 2.5 Flash, Pillow, Decimal auditing, Supabase persistence, and (when `SARVAM_API_KEY` is configured) Sarvam Bulbul v4 Flash TTS. `PARCHA_TTS_LANGUAGE` defaults to `hi-IN`; generated audio is returned through `/static/audio/`. Missing key/provider failure keeps the transcript speech fallback. The current local `.env` has no key yet, so Sarvam playback is pending a rotated key and live smoke check. TTS has a 5-second request timeout and can extend scan response time. `load-sample` remains fixture-verbatim and resolve are REST-only; resolve does not emit `PAYOUT_APPROVED` because the frontend also applies the REST response. The UPI Autopay badge is a stored/demo state, not a live mandate registration.

### Flow Details
1. **State 1: IDLE**
   * Laptop screen shows `"Awaiting supplier parcha..."` with today's collections.
   * Soundbox twin screen indicates `"Ready for the next parcha"`.
2. **State 2: PROCESSING (~1.5s - 3s)**
    * Merchant snaps a photo on the phone or selects a bill using the laptop's **Upload Bill** button.
    * The client sends `POST /api/parcha/scan`.
   * Realtime WebSocket pushes `{"event": "SCAN_STARTED"}` to the laptop.
   * Laptop Soundbox screen immediately animates with a laser-sweep: `"Auditing Parcha... Gemini 2.5 Flash / Decimal audit / Mandi-Pulse"`.
3. **State 3: AUDIT ALERT**
   * Realtime WebSocket pushes `{"event": "AUDIT_COMPLETE"}`.
    * **Voice Alert:** Once a rotated `SARVAM_API_KEY` is set in root `.env`, the Soundbox plays generated Hindi WAV audio. Without a valid key or when the provider fails, use the tap-to-speak browser transcript fallback.
   * **Front Screen:** Shows red overcharge warning `⚠ Overcharge ₹140 · Pay ₹13,860`.
   * **Audit Table:** Shows red row for Fortune Oil (rate hike + pen edit from 12 to 10), yellow row for Parle-G (76% OCR confidence review), Mandi-Pulse benchmark badge, and pen strikethrough crop.
4. **State 4: RESOLVED & FINANCED**
   * Merchant presses the physical 3D **Paytm Button** on the Soundbox twin.
   * Sends `POST /api/parcha/{id}/resolve` with `{"action": "APPROVE_SPLIT", "tenure_days": 7}`.
    * `POST /api/parcha/{id}/resolve` returns the payout/loan schedule; the counter applies the REST response (no payout WS event).
      * **WhatsApp Drawer:** Slides out showing the distributor message preview, crop proof when present, and Paytm payment link preview.
     * **GST IMS Shield:** Flips status to `Shield Active · DISPUTED_PENDING_IMS` (protects before 14th of month).
     * **7-Day Soundbox Split:** Displays 7-day schedule (Day 1 ₹1,980 deducted from QR sweep, remaining ₹11,880, backup UPI Autopay active).

---

## 4. Local Execution & Docker Commands

### Run Full Stack (Frontend + API Gateway)
```bash
docker compose up --build
```

### Run Frontend Alone (UI only)
```bash
docker compose up --build -d --no-deps frontend
```
The integrated frontend no longer falls back to a local mock API; backend-backed actions require the API service.

### Rebuilding after Frontend Changes
```bash
docker compose up --build -d --no-deps frontend
```

---

## 5. Architectural Contracts Cheat Sheet

### Core REST Endpoints
* `POST /api/parcha/scan` — Multipart form (`file`, `merchant_id`).
* `POST /api/parcha/{id}/resolve` — Body: `{"action": "APPROVE_SPLIT", "tenure_days": 7}`.
* `POST /api/demo/load-sample` — Body: `{"sample_id": "sample_pen_edit_01"}`.
* `GET /api/parcha/{id}/export?format=tally|marg` — Downloads purchase voucher XML/CSV.

### WebSocket Events (`/ws/counter`)
* `SCAN_STARTED`: Dispatched within <0.5s of file upload.
* `AUDIT_COMPLETE`: Dispatched within <3.5s with itemized discrepancies and audio URL.
* Resolve is REST-only in the current integration. `PAYOUT_APPROVED` remains in the CIS type contract but is not emitted until the frontend's duplicate-apply path is coordinated.

### Immutable Financial Rules
* **Zero LLM Math:** All calculations done using Python `decimal.Decimal`.
* **True Landed Unit Cost:**
  `(Net Line Amount + GST) / (Billed Qty + Free Qty)`
* **7-Day Credit Velocity Cap:**
  `Daily Cap = 30-Day Avg Daily QR Volume * 0.35`
  `Max Credit Limit = Daily Cap * 7`
* **Mandi-Pulse Guardrail:** Uses the median of eligible invoice-history rates and activates only when >= 5 distinct stores have purchased the canonical SKU in that pin code over the last 14 days.

---

## 6. Pitch Day Troubleshooting & Safeguards

1. **Browser Audio Autoplay Block:** Modern browsers restrict audio autoplay until the user interacts with the page. If the audio doesn't automatically speak on `/counter`, click the pulsing **"🔊 Tap to hear the audit"** button that appears on the Soundbox twin.
2. **Fail-Safe "Load Sample" Button:** If mobile network latency spikes or lighting ruins camera capture during the pitch, click **"Load Sample"** on `/counter`. It returns the CIS golden fixture via REST; it does not broadcast WebSocket events or write an invoice.
3. **Resetting Between Judges / Demos:** Click the **"Reset demo"** button on the top-right topbar of `/counter` to instantly return the Soundbox twin to its idle state.

