# shreyas.md — Module 2 Slice 1 (REST API Gateway) — What Was Built & How to Integrate

Author: Dev 2 session · 2026-10-31 · Plan referenced: `.opencode/plans/module2-rest-api-plan.md` ·
Living context: `AGENTS.md` · Contracts source of truth: ED Part 2 (CIS) + `contracts/contracts.ts` — never this file.

## 1. What this slice is

The FastAPI gateway (`backend/`, runs as `app.main:app` on 8000 via uvicorn) implementing the
**four CIS §4 REST endpoints only**. WebSocket (`/ws/counter`), `/static` mounting, and the real
Gemini/audit pipeline are explicitly NOT in this slice — they are next slices.

| Endpoint | Status |
|---|---|
| `POST /api/parcha/scan` | ✅ live — validates multipart (≤20 MB, jpeg/png/pdf), resolves merchant, calls the pipeline seam (provisional fixture), returns `AuditedInvoiceResponse` |
| `POST /api/parcha/{id}/resolve` | ✅ live — real DB writes (loan + IMS upsert + invoice status), Decimal math, 404/409/422 guards |
| `GET /api/parcha/{id}/export?format=tally\|marg` | ✅ live — real Tally XML / Marg CSV generated from line items only |
| `POST /api/demo/load-sample` | ✅ live — CIS §5 golden fixture verbatim, no DB writes, never broadcasts (B2) |
| `GET /healthz` | ✅ operational probe (additive, documented as outside the CIS REST table) |

## 2. Files (high level)

- `app/main.py` — FastAPI app; registers routers; `lifespan` wires the two provisional seams; `/healthz`.
- `app/contracts.py` — Pydantic models mirroring `contracts.ts` / CIS §5 field-for-field (casing immutable).
- `app/core/config.py` — env snapshot (`SUPABASE_*`, `PARCHA_DEMO_MERCHANT_ID`, `PARCHA_FIXTURE_PATH`, upload limits). Loads ROOT `.env` only.
- `app/core/db.py` — shared async Supabase client (pre-existing) + NEW `reset_client()` (test-only loop-rebinding escape).
- `app/core/money.py` — Decimal helpers: `q2` (2-dp HALF_UP), `dec` (float-safe via str), `as_float` (serialize to JSON number).
- `app/core/repo.py` — the ONLY DB access: reads (`get_merchant`, `get_invoice_bundle` w/ supplier+line-item join, `get_loan_for_invoice`, `get_ims_record_for_invoice`) and writes (`insert_loan`, `insert_ims_record`, `update_ims_status`, `update_invoice_status`).
- `app/api/scan_router.py`, `resolve_router.py`, `export_router.py`, `demo_router.py`.
- `app/services/pipeline.py` — **SEAM 1** (`ParchaPipeline` protocol).
- `app/services/credit_rules.py` — **SEAM 2** (`CreditRules` protocol).
- `app/services/merchant_resolver.py` — B1 demo-merchant chain.
- `app/services/exporters.py` — Tally XML + Marg CSV builders (Module 5 deliverable, gateway-exposed).

## 3. The two integration mocks (and exactly how to replace them)

Everything else is real (Supabase, Decimal, contracts, exports). Only the two teammate seams are provisional:

### SEAM 1 — `ParchaPipeline` (`services/pipeline.py`) → Module 3+4 (Gemini + audit)
- **Current:** `FixturePipeline` returns the CIS §5 golden fixture for every scan; **zero DB writes** (protects seeded invariants).
- **Interface contract for Module 3/4:** `async extract_and_audit(image_bytes: bytes, content_type: str, merchant: dict) -> AuditedInvoiceResponse`. `merchant` is a raw `merchants` row.
- **To integrate:** call `set_pipeline(MyRealPipeline())` at startup — signature exists in `main.py` lifespan. No router/main/app changes needed. When real, the pipeline owns: persisting invoice + line items, crop/audio URLs (→ `/static` slice), WS broadcast of `SCAN_STARTED`/`AUDIT_COMPLETE` (via the next slice's ws_manager).

### SEAM 2 — `CreditRules` (`services/credit_rules.py`) → Module 4 (credit engine)
- **Current:** `ProvisionalCreditRules`: `cap = 0.35 × merchant.avg_daily_qr_volume` (stored column source, matching seed invariants — NOT recomputed from `transactions`), `daily = (principal/tenure).q2`, `remaining = principal − daily` (Day-1 sweep booked, per fixture semantics).
- **Interface contract for Module 4:** `plan(merchant: dict, principal: Decimal, tenure_days: int) -> CreditPlan(daily_cap, principal, daily_deduction, remaining_balance)`.
- **To integrate:** `set_credit_rules(MyEngine())` at startup. Module 4 should also take over: the full pipeline call above can then use its audit engine for pre-approval fields.
- Known untouched tension (do-not-silently-fix): golden-fixture cap 3500 vs seed-derived caps differ; parser picks stored column.

## 4. Decisions baked into the gateway (integration must respect)

1. **B1 (frontend merchant id never fixed):** `resolve_merchant()` chain = exact `merchants` lookup → `PARCHA_DEMO_MERCHANT_ID` env → first seeded merchant owning an invoice. Env is set to `893054e0-9d6a-5a7c-955f-a36201ce39e6` (Sharma Kirana Store 11: RATE_HIKE-bearing history + exactly one clean resolve target: invoice `d7b23a11-bf76-55dc-80b3-e027c52931d9` / INV-2026-0051, AUDITED + loan-free). Use that invoice as the on-stage resolve demo.
2. **B2 (WS broadcast policy for next slice):** broadcast only for REAL scans (`SCAN_STARTED` + `AUDIT_COMPLETE`); resolve broadcasts `PAYOUT_APPROVED`; `/api/demo/load-sample` NEVER broadcasts (frontend applies REST response directly — double-apply otherwise).
3. **Resolve is UPSERT-side IMS:** every seeded invoice already has an IMS row, so resolve updates `ims_status → 'PENDING'` (vocab map: invoice-status `DISPUTED_PENDING_IMS` ↔ ims `PENDING`) and inserts only when absent. 1-IMS-row-per-invoice stays true.
4. **Resolve replay safety:** second resolve → 409 (loan exists) or 409 (status SETTLED). PostgREST has no cross-table tx — writes are best-effort sequenced (IMS → loan → invoice status) with stage-tagged 500s on partial failure.
5. **Line-item math rule:** export (and future invoice persistence) derives amounts from `invoice_line_items` only; stored `billed_total` includes freight and is never used.
6. **Money:** Decimal end-to-end (`app/core/money.py`); wire JSON floats are str-marked to avoid binary drift. When writing rows, pass `str(q2(value))`.

## 5. Verification status (as of 2026-10-31)

- ✅ In-process (Starlette TestClient, host run): all endpoints + guards; real Supabase reads; one full resolve→rollback cycle proving exact write math (loan 4935.06/705.01/2676.80/4230.05, IMS upsert, status flip) with DB restored pristine (56 loans / 150 IMS / AUDITED).
- ⏳ Deferred (Docker Desktop was broken): `docker compose up --build` both-services-healthy check + browser-through-proxy smoke (load a `/counter` → Load Demo Bill → real 200 from api). compose.yaml api now mounts `./contracts:/contracts:ro` for the fixture; `.env.example` documents the new vars.

## 6. Next slices (in order)

1. **WS slice:** `/ws/counter` (envelope `{event, data}`; `SCAN_STARTED <0.5s`, `AUDIT_COMPLETE <3.5s`, `PAYOUT_APPROVED`) honoring B2 — scaffold placeholder is `app/core/ws_manager.py`.
2. **/static slice:** serve crops/audio behind the 4200 proxy when the real pipeline produces them.
3. **Pipeline wiring:** Module 3/4 land their impls → two `set_*` calls in `main.py` lifespan, delete `FixturePipeline`/`ProvisionalCreditRules`.
