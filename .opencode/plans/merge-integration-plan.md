# Full-Stack Merge & Integration Plan (`shreyas` + `soumya` + `suhas` → `main`)

**Date:** 2026-10-31 · **Status:** merged/integrated; host-verified; Docker/Gemini end-to-end checks pending

---

## 0. Branch Assessment & Real Discrepancies / Bugs (Not Auto-Fixed by `git merge`)

### What each branch brings
- **`origin/shreyas` (Module 2 & 5):** FastAPI gateway (`scan`, `resolve`, `export`, `load-sample`, `/ws/counter`, `/static`, `/healthz`), Supabase repository layer (`app/core/repo.py`), B1 merchant resolver (`app/services/merchant_resolver.py`), Tally XML & Marg CSV exporters (`app/services/exporters.py`), and two integration seams (`ParchaPipeline` and `CreditRules`).
- **`origin/suhas` (Module 3 + Frontend updates):** Live Gemini 2.5 Flash vision extraction (`app/services/gemini_vision.py`), Pillow contextual dispute cropper (`app/services/pillow_cropper.py`), CIS §3 vision models in `contracts/contracts.py`, laptop bill upload button in `counter.component.ts`, and live-API-only `api.service.ts` (mock fallback removed). Also includes a standalone in-memory `scan_router.py`/`resolve_router.py` that mocked Module 4 & DB persistence.
- **`origin/soumya` (Module 4):** Pure `Decimal` engines (`app/engine/math_engine.py`, `waterfall_engine.py`, `credit_engine.py`), Supabase query + service layers (`app/bill_validation/`, `app/price_analysis/`, `app/credit/`), `RequestLoggingMiddleware` (`app/core/logging_config.py`), and offline unit tests (`backend/tests/`).

### Discrepancies, Mismatches & Bugs to Fix During Integration
*(Excluding normal file overlaps resolved simply by combining routers/imports during merge)*

1. **[BUG — Crash in `suhas` `load_sample`]**
   - In `origin/suhas:backend/app/api/scan_router.py` (line 258), `load_sample()` passes `unit_rate=240.00` instead of `billed_rate=240.00` to `AuditedItem`. Because `AuditedItem` requires `billed_rate`, calling `POST /api/demo/load-sample` on `suhas` throws a Pydantic `ValidationError` (HTTP 500).
   - **Resolution:** Keep `shreyas`'s `demo_router.py` implementation, which validates and serves `contracts/demo_bill_fixture.json` verbatim.

2. **[MISMATCH — Missing DB Persistence & SKU/Supplier Resolution Between `suhas` (Module 3) and `soumya`/`shreyas` (Modules 4 & 5)]**
   - `suhas`'s scan route keeps audited bills only in an in-memory dictionary (`invoices_store[invoice_id]`) and hardcodes `personal_history_rate = unit_rate` and `mandi_pulse_median = unit_rate`.
   - However, `soumya`'s Module 4 services (`validate_bill`, `analyze_invoice_prices`, `get_credit_recommendation`) and `shreyas`'s `POST /api/parcha/{id}/resolve` & `GET /api/parcha/{id}/export` read from **live Supabase tables** (`invoices`, `invoice_line_items`, `suppliers`, `canonical_skus`). Furthermore, `soumya`'s `analyze_invoice_prices` skips supplier-history and pincode-peer queries if `supplier_id` or `canonical_sku_id` is `None`.
   - Also, `embedding_client.py` is unimplemented across all branches and `canonical_skus.embedding` is `NULL` in the seeded DB; SKU resolution must therefore use the CIS fallback (`canonical_skus.product_name` and `aliases` text matching).
   - **Resolution:** In the integrated `ParchaPipeline`:
      1. Run `suhas`'s `extract_invoice_from_image()` and `crop_pen_markup()`.
      2. Match `supplier_gstin` / `supplier_name` exactly against `suppliers`; leave `supplier_id` null if no safe match (never misattribute a supplier). Match each line's `raw_item_name` against `canonical_skus` (`product_name` + `aliases`); leave unmatched SKUs null.
     3. Run `soumya`'s `math_engine.calculate_line` and `waterfall_engine.analyze_price` (fed by `soumya`'s `get_supplier_history` and `get_pincode_peer_rates`) + `credit_engine` 30-day QR velocity cap.
      4. Persist the new `invoices` row, `invoice_line_items` rows, and `gst_ims_records` (`PENDING`) row into Supabase so that `resolve`, `export`, the `/api/parcha/{id}/*` routes, and mounted read-only `/api/credit/*` GETs work on every scanned bill.

3. **[MISMATCH — `billed_total` vs `approved_total` & Weekly vs 7-Day Daily Credit Model]**
   - **CIS §4 & Counter UI contract:** `split_credit_pre_approval` and `POST /api/parcha/{id}/resolve` use a **7-day daily QR sweep** (`tenure_days: 7`) where principal is `approved_total` (after stripping pen-edit/rate overcharges), `daily_velocity_cap` is `0.35 × avg_daily_qr_volume` (from 30-day `transactions` or `merchants.avg_daily_qr_volume`), `max_credit_limit = daily_velocity_cap × 7`, and `daily_deduction_amount = approved_total / 7`.
   - **`soumya`'s `/api/credit/*`:** Built an additive weekly EMI simulation (`tenure_weeks`, `LOAN_DISBURSEMENT_SIMULATED`) that uses `invoice["billed_total"]` as principal instead of `approved_total`.
   - **Resolution:**
      - Keep compatible Module 4 credit GETs. Do not mount weekly-credit POST write routes while the approved ledger schema/vocabulary remains unchanged.
     - Wire `CreditRules` (used by `scan` pre-approval and `POST /api/parcha/{id}/resolve`) to compute the 30-day QR average using `soumya`'s `credit_engine.successful_qr_amount` / `get_transactions` (falling back to `merchant.avg_daily_qr_volume`), using `approved_total` as principal and 7-day daily deductions for the CIS counter flow.

4. **[MISMATCH — Waterfall Engine Output vs CIS `AuditedItem` Fields]**
   - `soumya`'s `waterfall_engine.analyze_price()` returns `supplier_history.median_rate` (or `None` if no prior purchases) and `pincode_benchmark.average_rate` (or `None` if `< 5` peer stores in the 14-day window), and does not format `mandi_pulse_band` (`"₹X - ₹Y"`).
   - **Resolution:** When mapping `analyze_price()` into `AuditedItem`:
     - `personal_history_rate` = `supplier_history.median_rate` if present, else `billed_rate`.
     - `mandi_pulse_median` = the median of eligible invoice-history peer rates when the ≥5 distinct-store/14-day gate is active; never map `average_rate` into this median field.
     - `mandi_pulse_band` = the median price band from eligible invoice-history rates, formatted in the CIS shape (`"₹X - ₹Y"`); keep the <5-store gate inactive.
     - `discrepancy_type` = combines pen-edit/math checks from `math_engine` + `suhas` with `rate_status == "FLAGGED_HIGH"` from `waterfall_engine` and `< 0.80` OCR confidence.

5. **[MISMATCH — WebSocket Broadcast Policy & Laptop Scan Double-Apply]**
   - `suhas` added a "📷 Upload Bill" button directly on `/counter` (`onLaptopFileSelected`) which calls `api.scan(file)` and then `this.applyAudit(audit)` on the REST response, while `/counter` is simultaneously subscribed to `ws.auditComplete$`.
   - In `suhas`'s `resolve_router.py` and `load_sample`, broadcasting `AUDIT_COMPLETE` and `PAYOUT_APPROVED` causes `/counter` to apply both the WS event and the REST response.
   - **Resolution:** Keep `shreyas`'s WS policy (`SCAN_STARTED` + `AUDIT_COMPLETE` broadcast only on `POST /api/parcha/scan`; `load-sample` and `resolve` are REST-only), and in `counter.component.ts` make `applyAudit` / `applyPayout` idempotent on `invoice_id` so uploading from laptop `/counter` or phone `/scan` transitions smoothly without double re-rendering.

6. **[RESOLVED POLICY — Hold Module 4 weekly-credit write routes; keep schema unchanged]**
   - Root `AGENTS.md` documents `merchant_account_ledger.kind` as `OPENING | LOAN_DEDUCT | QR_CREDIT | REFUND`. Soumya's `/api/credit/*` implementation writes `LOAN_DISBURSEMENT_SIMULATED`, `WEEKLY_EMI_PAID:*`, `WEEKLY_EMI_MISSED:*`, and `WEEKLY_EMI_PARTIAL:*`, and relies on those values to distinguish weekly loans and missed-payment alerts.
   - User decision: keep the schema unchanged and hold the weekly-credit write routes. Do not mount `POST /api/credit/{invoice_id}/accept` or `POST /api/credit/loans/{loan_id}/simulate-week`; preserve compatible read-only GET routes (recommendation, schedule, alerts) only. Do not add DDL or alter the approved kind vocabulary.
   - Read-only inspection found one non-seed loan and two associated ledger rows already using `LOAN_DISBURSEMENT_SIMULATED` and `WEEKLY_EMI_PAID:1`. These live rows remain untouched; their existence does not change the approved contract.

7. **[SOURCE-OF-TRUTH CORRECTION — Mandi-Pulse is a median, not the Module 4 peer average]**
   - The approved data decision and CIS require a median price band from invoice history with the ≥5 distinct-store/14-day gate. Soumya's `waterfall_engine` computes a per-store average and then an average across stores. The previous plan incorrectly proposed mapping that average directly to `mandi_pulse_median`.
   - **Integration rule:** compute/report the CIS-required median for the Mandi-Pulse payload; never label an average as a median.

8. **[BUG — Weekly simulator searches backward from loan creation]**
   - `soumya.md` describes successive non-overlapping seven-day windows anchored at loan creation. `simulate_credit_week()` currently sets week 1 to the seven days *before* creation and moves farther backward for later weeks, while stamping the ledger due date after creation.
   - **Integration fix:** use forward, non-overlapping windows from loan creation (`created_at + (week-1)*7` through the next seven days), while preserving the documented simulated-only semantics.

9. **[BLOCKER — CIS does not define how a flagged rate hike changes `approved_total`]**
   - The real pipeline must produce `billed_total`, `approved_total`, and `overcharge_amount`. CIS/PRD require math checks and price flags but do not state whether an above-history/Mandi-Pulse `billed_rate` is automatically repriced for the payout. The fixture's invoice totals do not reconcile to its line items, so it cannot safely settle the formula.
   - Soumya's engine flags higher prices but does not compute a replacement approved rate. Suhas's scan code sums corrected quantities at the billed rate and compares against the printed grand total, which can include freight/non-itemized charges; that also cannot be carried over as-is.
   - **User decision:** rate hikes are flagged/reconciled but not auto-repriced. `approved_total` is the Decimal sum of line totals at the invoiced rate using the Gemini-extracted accepted `billed_qty` (after real pen edits); `overcharge_amount` is the sum of positive printed-line-total minus recomputed accepted line-total differences. The invoice-level printed grand total remains `billed_total` for display only and is not used for overcharge/underwriting (it can contain freight/non-itemized charges). This drives WhatsApp amount and CIS credit principal.

---

## 1. Scope & Non-Goals

### Scope
- Merge `origin/shreyas`, `origin/soumya`, and `origin/suhas` into `main`.
- Replace `FixturePipeline` with the real integrated `LiveParchaPipeline` (Gemini 2.5 Flash extraction $\rightarrow$ Pillow dispute crop $\rightarrow$ Supplier/SKU lookup $\rightarrow$ Soumya's `math_engine` + `waterfall_engine` + `credit_engine` $\rightarrow$ Supabase persistence).
- Replace `ProvisionalCreditRules` with `LiveCreditRules` backed by Soumya's `credit_engine` + 30-day `transactions` query (with `avg_daily_qr_volume` fallback).
- Register all CIS §4 routes (`/api/parcha/scan`, `/api/parcha/{id}/resolve`, `/api/parcha/{id}/export`, `/api/demo/load-sample`, `/ws/counter`, `/static`) alongside Soumya's validation/price routes and compatible read-only `/api/credit/*` GETs plus `RequestLoggingMiddleware`. Weekly-credit POST writes stay unmounted per the user decision.
- Keep all existing documentation files (`shreyas.md`, `soumya.md`, `suhas.md`, `DEMO_REFERENCE_GUIDE.md`) and update `AGENTS.md`.

### Non-Goals
- No new product features or schema changes.
- No Sarvam TTS external API call if no implementation exists in any branch (keep `/static/audio/...` contract URL with the frontend's existing `speechSynthesis` voice transcript fallback).
- Do not `git push` (user handles push).

---

## 2. Contract References

- **CIS §2 (DDL):** `merchants`, `suppliers`, `canonical_skus`, `invoices`, `invoice_line_items`, `gst_ims_records`, `split_credit_loans` + approved `transactions` and `merchant_account_ledger`.
- **CIS §3 (Vision Schema):** `BoundingBox2D`, `ExtractedLineItem`, `RawExtractedInvoice`.
- **CIS §4 (REST & WS):** `/api/parcha/scan`, `/api/parcha/{id}/resolve`, `/api/parcha/{id}/export`, `/api/demo/load-sample`, `/ws/counter` (`SCAN_STARTED`, `AUDIT_COMPLETE`, `PAYOUT_APPROVED`).
- **CIS §5 (Golden Fixture):** `contracts/demo_bill_fixture.json`.

---

## 3. Step-by-Step Merge & Integration Tasks

1. **Fast-forward / merge `origin/shreyas` into `main`:**
   - Brings in the clean Module 2/5 gateway, `ws_manager.py`, `repo.py`, `exporters.py`, `demo_router.py`, and `shreyas.md`.
2. **Merge `origin/soumya` into `main`:**
    - Resolve `backend/app/main.py`, `backend/app/core/db.py`, and `AGENTS.md` conflicts by combining `shreyas`'s 9-table smoke check + `reset_client()` with `soumya`'s logger statements, and mounting `soumya`'s `RequestLoggingMiddleware`, `bill_validation`, `price_analysis`, and read-only `credit` router in `main.py`.
3. **Merge `origin/suhas` into `main`:**
   - Keep `suhas`'s `gemini_vision.py`, `pillow_cropper.py`, `suhas.md`, sample crop JPEGs, and frontend `/counter` upload button (`counter.component.ts`, `api.service.ts`).
   - Unify `contracts/contracts.py` and `backend/app/contracts.py` so both CIS §3 (`BoundingBox2D`, `ExtractedLineItem`, `RawExtractedInvoice`) and CIS §4 models are exported cleanly.
   - Unify `backend/app/core/config.py` so `Settings` includes `url`, `secret_key`, `demo_merchant_id`, `gemini_api_key`, and `static_dir`.
   - In `compose.yaml`, mount `./contracts:/contracts:ro` (and support both `/contracts` and repo-root resolution).
4. **Wire the Real Pipeline (`backend/app/services/pipeline.py` & `credit_rules.py`):**
   - Apply the user-approved amount rule in item 9; do not reprice a flagged rate.
   - Implement `LiveCreditRules` using `soumya`'s `get_transactions` + `successful_qr_amount` (30-day window, with `avg_daily_qr_volume` fallback) and `0.35` daily velocity cap.
   - Implement `LiveParchaPipeline`:
     - Calls `gemini_vision.extract_invoice_from_image(image_bytes, mime_type)`
     - Uses Gemini's extracted quantities without hard-coded demo-specific correction (do not carry forward Suhas's `12 -> 10` rewrite); uses `pillow_cropper.crop_pen_markup(...)` for actual detected markup.
     - Resolves `supplier_id` and `canonical_sku_id` against Supabase (`suppliers` & `canonical_skus` aliases)
     - Runs `soumya`'s `math_engine.calculate_line` and `waterfall_engine.analyze_price` (with `get_supplier_history` and `get_pincode_peer_rates`)
     - Fetches supplier/SKU catalogs and per-SKU history/peer data concurrently (deduplicated for repeated SKUs) to limit scan latency toward the CIS 3.5-second target.
     - Computes `split_credit_pre_approval` via `LiveCreditRules`
     - Persists `invoices`, `invoice_line_items`, and `gst_ims_records` (`PENDING`) to Supabase via `repo.py`
     - Returns `AuditedInvoiceResponse` (while `load-sample` continues to use `FixturePipeline` for the golden fixture).
   - Preserve scan upload type/size validation and the approved scan-only WebSocket event policy.
   - Keep the ledger-kind policy above: `/api/credit/*` write routes remain unavailable; do not silently change the approved ledger schema.
5. **Local Verification (Host TestClient + Unit Tests):**
   - Run Soumya's unit test suite: `python -m unittest discover -s tests -v`.
   - Run `python -m app.core.db` smoke check (all 9 tables).
   - Run end-to-end integration tests with `TestClient`:
     - `/healthz`, `/api/demo/load-sample`, `/static/crops/...`
     - `/api/parcha/{id}/validate`, `/alerts`, `/price-analysis`, `/api/credit/{id}/recommendation`
     - `/api/parcha/{id}/export?format=tally|marg`
     - Simulated/real scan pipeline + `/ws/counter` broadcast + `/api/parcha/{id}/resolve` with DB rollback.
   - Update `AGENTS.md` with the final integrated architecture and verification status.

---

## 4. Definition of Done

- [x] `shreyas`, `soumya`, and `suhas` are integrated into `main`; conflict-marker search is clean.
- [x] Uploaded scans use Gemini + Pillow + Module 4 Decimal/median-price logic + Supabase invoice/line/IMS persistence. CIS daily-credit underwriting is transaction-backed. The golden fixture remains only for the explicit `load-sample`; weekly-credit write routes remain unmounted by user decision.
- [x] `python -m unittest discover -s tests -v` passes (23 tests).
- [x] Host TestClient checks cover CIS routes, WS scan event order/shape, static files, Module 4 read APIs, and live resolve with rollback. 9-table smoke is reachable; live DB started and ended with the same state (57 loans/177 ledger; the extra loan/two ledger rows predated these checks).
- [ ] Docker Compose/browser-proxy verification (Docker CLI unavailable on this laptop).
- [ ] Real Gemini bill upload test (not run to avoid an external API call and new live invoice without an explicitly selected test bill).
- [x] `AGENTS.md` and integration docs updated; nothing pushed (`git push` reserved for user).
