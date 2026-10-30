# shreyas.md — Module 2 (REST + WebSocket + Static) — What Was Built & How to Integrate

Author: Dev 2 session · 2026-10-31 · Plans: `.opencode/plans/module2-rest-api-plan.md`, `.opencode/plans/module2-websocket-static-plan.md` ·
Living context: `AGENTS.md` · Contracts source of truth: ED Part 2 (CIS) + `contracts/contracts.ts` — never this file.

## 1. What this slice is

The FastAPI gateway (`backend/`, `app.main:app`, port 8000) implements the four CIS §4 REST
endpoints, `/ws/counter`, `/static`, and `/healthz`. Gemini/audit processing remains behind the
provisional pipeline seam.

| Endpoint | Status |
|---|---|
| `POST /api/parcha/scan` | ✅ live — validates multipart (≤20 MB, jpeg/png/pdf), resolves merchant, calls the pipeline seam (provisional fixture), returns `AuditedInvoiceResponse` |
| `POST /api/parcha/{id}/resolve` | ✅ live — real DB writes (loan + IMS upsert + invoice status), Decimal math, 404/409/422 guards |
| `GET /api/parcha/{id}/export?format=tally\|marg` | ✅ live — real Tally XML / Marg CSV generated from line items only |
| `POST /api/demo/load-sample` | ✅ live — CIS §5 golden fixture verbatim, no DB writes, never broadcasts (B2) |
| `GET /healthz` | ✅ operational probe (additive, documented as outside the CIS REST table) |
| `WS /ws/counter` | ✅ live — broadcasts `SCAN_STARTED` then `AUDIT_COMPLETE` for uploaded scans to all connected counters |
| `/static/*` | ✅ live — serves `backend/static/`; fixture crop is present, absent WAV intentionally returns 404 |

## 2. Files (high level)

- `app/main.py` — FastAPI app; registers routers; `lifespan` wires the two provisional seams; `/healthz`.
- `app/contracts.py` — Pydantic models mirroring `contracts.ts` / CIS §5 field-for-field (casing immutable).
- `app/core/config.py` — env snapshot (`SUPABASE_*`, `PARCHA_DEMO_MERCHANT_ID`, `PARCHA_FIXTURE_PATH`, upload limits). Loads ROOT `.env` only.
- `app/core/db.py` — shared async Supabase client (pre-existing) + NEW `reset_client()` (test-only loop-rebinding escape).
- `app/core/money.py` — Decimal helpers: `q2` (2-dp HALF_UP), `dec` (float-safe via str), `as_float` (serialize to JSON number).
- `app/core/repo.py` — the ONLY DB access: reads (`get_merchant`, `get_invoice_bundle` w/ supplier+line-item join, `get_loan_for_invoice`, `get_ims_record_for_invoice`) and writes (`insert_loan`, `insert_ims_record`, `update_ims_status`, `update_invoice_status`).
- `app/api/scan_router.py`, `resolve_router.py`, `export_router.py`, `demo_router.py`.
- `app/api/ws_router.py` + `app/core/ws_manager.py` — app-scoped connection registry, broadcast envelope, disconnect cleanup.
- `backend/static/crops/demo_pen_edit.jpg` — visibly labeled demo-only placeholder, not a Gemini crop. `backend/static/audio/demo_alert.wav` is intentionally absent so the frontend can offer transcript/TTS fallback.
- `app/services/pipeline.py` — **SEAM 1** (`ParchaPipeline` protocol).
- `app/services/credit_rules.py` — **SEAM 2** (`CreditRules` protocol).
- `app/services/merchant_resolver.py` — B1 demo-merchant chain.
- `app/services/exporters.py` — Tally XML + Marg CSV builders (Module 5 deliverable, gateway-exposed).

## 3. The two integration mocks (and exactly how to replace them)

Everything else is real (Supabase, Decimal, contracts, exports). Only the two teammate seams are provisional:

### SEAM 1 — `ParchaPipeline` (`services/pipeline.py`) → Module 3+4 (Gemini + audit)
- **Current:** `FixturePipeline` returns the CIS §5 golden fixture for every scan; **zero DB writes** (protects seeded invariants).
- **Interface contract for Module 3/4:** `async extract_and_audit(image_bytes: bytes, content_type: str, merchant: dict) -> AuditedInvoiceResponse`. `merchant` is a raw `merchants` row.
- **To integrate:** call `set_pipeline(MyRealPipeline())` at startup — signature exists in `main.py` lifespan. `scan_router` owns `SCAN_STARTED`/`AUDIT_COMPLETE` around the pipeline call; the pipeline returns the audited response and must keep the same `AuditedInvoiceResponse` contract. Real crop/audio files use the existing `/static/crops/` and `/static/audio/` directories and Compose volumes.

### SEAM 2 — `CreditRules` (`services/credit_rules.py`) → Module 4 (credit engine)
- **Current:** `ProvisionalCreditRules`: `cap = 0.35 × merchant.avg_daily_qr_volume` (stored column source, matching seed invariants — NOT recomputed from `transactions`), `daily = (principal/tenure).q2`, `remaining = principal − daily` (Day-1 sweep booked, per fixture semantics).
- **Interface contract for Module 4:** `plan(merchant: dict, principal: Decimal, tenure_days: int) -> CreditPlan(daily_cap, principal, daily_deduction, remaining_balance)`.
- **To integrate:** `set_credit_rules(MyEngine())` at startup. Module 4 should also take over: the full pipeline call above can then use its audit engine for pre-approval fields.
- Known untouched tension (do-not-silently-fix): golden-fixture cap 3500 vs seed-derived caps differ; parser picks stored column.

## 4. Decisions baked into the gateway (integration must respect)

1. **B1 (frontend merchant id never fixed):** `resolve_merchant()` chain = exact `merchants` lookup → `PARCHA_DEMO_MERCHANT_ID` env → first seeded merchant owning an invoice. Env is set to `893054e0-9d6a-5a7c-955f-a36201ce39e6` (Sharma Kirana Store 11: RATE_HIKE-bearing history + exactly one clean resolve target: invoice `d7b23a11-bf76-55dc-80b3-e027c52931d9` / INV-2026-0051, AUDITED + loan-free). Use that invoice as the on-stage resolve demo.
2. **WS policy:** uploaded scans broadcast `SCAN_STARTED` + `AUDIT_COMPLETE`; `/api/demo/load-sample` and resolve are REST-only. Resolve's `PAYOUT_APPROVED` broadcast is explicitly withheld (user-approved CIS §4 Event 3 deviation) because the current frontend applies the REST response directly too. Do not silently change this; coordinate with Dev 1 before enabling Event 3.
3. **Resolve is UPSERT-side IMS:** every seeded invoice already has an IMS row, so resolve updates `ims_status → 'PENDING'` (vocab map: invoice-status `DISPUTED_PENDING_IMS` ↔ ims `PENDING`) and inserts only when absent. 1-IMS-row-per-invoice stays true.
4. **Resolve replay safety:** second resolve → 409 (loan exists) or 409 (status SETTLED). PostgREST has no cross-table tx — writes are best-effort sequenced (IMS → loan → invoice status) with stage-tagged 500s on partial failure.
5. **Line-item math rule:** export (and future invoice persistence) derives amounts from `invoice_line_items` only; stored `billed_total` includes freight and is never used.
6. **Money:** Decimal end-to-end (`app/core/money.py`); wire JSON floats are str-marked to avoid binary drift. When writing rows, pass `str(q2(value))`.

## 5. Verification status (as of 2026-10-31)

- ✅ In-process (Starlette TestClient, host run): all endpoints + guards; real Supabase reads; one full resolve→rollback cycle proving exact write math (loan 4935.06/705.01/2676.80/4230.05, IMS upsert, status flip) with DB restored pristine (56 loans / 150 IMS / AUDITED).
- ✅ Host TestClient verified two simultaneous WS clients each receive `SCAN_STARTED` → `AUDIT_COMPLETE`, exact narrow event shape vs wider REST response, reconnect/disconnect cleanup, and no extra event from sample-load, resolve, or invalid scan. Static crop returns `image/jpeg`; missing WAV, unknown path, and directory listing return 404.
- ⏳ Deferred (Docker Desktop unavailable): `docker compose up --build` health check + browser-through-proxy smoke for `/ws` and `/static`. Existing Compose mounts persist crops/audio; backend also mounts `./contracts:/contracts:ro` for the fixture.
- Live DB had one pre-existing non-seed loan + two related ledger rows before this slice's write-path check (57 loans / 177 ledger vs seed baseline 56 / 175). These were left untouched; temporary test resolve was rolled back and the demo invoice is AUDITED/ACCEPTED with no loan.

## 6. Next slices (in order)

1. **Docker verification:** once Docker Desktop works, build and test both services plus the 4200 `/ws` and `/static` proxy paths.
2. **Pipeline wiring:** Module 3/4 land their impls → replace `FixturePipeline`/`ProvisionalCreditRules` via the `set_*` seam calls; real pipeline assets populate the existing static directories.
3. **Resolve Event 3:** only after coordinating with Dev 1 to prevent the current REST+WS double-apply, revisit the explicitly withheld `PAYOUT_APPROVED` broadcast.

## 7. Quick host-only API test (no Docker, no frontend)

From the repository root (requires the existing `.env` and backend Python dependencies):

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`. `/healthz`, `POST /api/demo/load-sample`, exports, and static URLs are easy read-only checks. `POST /api/parcha/scan` emits two WS events to a connected `/ws/counter` client; Swagger alone does not display them, so use a WS client (e.g. browser devtools/`websocat`) alongside the POST. **Resolve writes to live Supabase**; it is intentionally not a harmless read-only test. Stop uvicorn with Ctrl+C.
