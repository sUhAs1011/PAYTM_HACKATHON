# shreyas.md — Integrated ParchaPay Backend — What Was Built & How to Integrate

Author: Dev 2 session · 2026-10-31 · Plans: `.opencode/plans/module2-rest-api-plan.md`, `.opencode/plans/module2-websocket-static-plan.md` ·
Living context: `AGENTS.md` · Contracts source of truth: ED Part 2 (CIS) + `contracts/contracts.ts` — never this file.

## 1. Integrated backend status

The FastAPI gateway (`backend/`, `app.main:app`, port 8000) combines the CIS §4 REST APIs,
`/ws/counter`, `/static`, Soumya's validation/price routes, and compatible credit GETs. Uploaded
scans use Gemini, Pillow, Decimal auditing, and Supabase persistence.

| Endpoint | Status |
|---|---|
| `POST /api/parcha/scan` | ✅ live — validates upload, resolves merchant, runs live pipeline and persistence, returns `AuditedInvoiceResponse` |
| `POST /api/parcha/{id}/resolve` | ✅ live — real DB writes (loan + IMS upsert + invoice status), Decimal math, 404/409/422 guards |
| `GET /api/parcha/{id}/export?format=tally\|marg` | ✅ live — real Tally XML / Marg CSV generated from line items only |
| `POST /api/demo/load-sample` | ✅ live — CIS §5 golden fixture verbatim, no DB writes, never broadcasts (B2) |
| `GET /healthz` | ✅ operational probe (additive, documented as outside the CIS REST table) |
| `WS /ws/counter` | ✅ live — broadcasts `SCAN_STARTED` then `AUDIT_COMPLETE` for uploaded scans to all connected counters |
| `/static/*` | ✅ live — serves `backend/static/`; fixture crop is present, fixture WAV is absent, generated scan WAVs are served |
| `/api/parcha/{id}/validate`, `/alerts`, `/price-analysis` | ✅ live — Module 4 Decimal validation and invoice-history price analysis |
| `/api/credit/*` GETs | ✅ live — read-only recommendations/schedule/alerts and daily-sweep projection |
| `/api/credit/*` POST writes | ⏸️ not mounted — keep ledger schema/kinds unchanged per user decision |

`GET /api/credit/{invoice_id}/sweep-preview` is an additive, read-only Module 4 route (not a CIS
endpoint). It returns the current Paytm-balance snapshot plus a recent-QR replay projection; it does
not persist Days 2–7 or the simulated bank-mandate fallback.

## 2. Files (high level)

- `app/main.py` — integrated FastAPI app; registers CIS + Module 4 read routes, logging, WS manager, static mount, and the live Gemini/audit services.
- `contracts/contracts.py` — single shared Pydantic contract source; `app/contracts.py` is the backend host/Docker bridge. TS casing remains aligned with CIS.
- `app/core/config.py` — env snapshot (`SUPABASE_*`, `PARCHA_DEMO_MERCHANT_ID`, `PARCHA_FIXTURE_PATH`, `SARVAM_API_KEY`, `PARCHA_TRANSLATION_SOURCE_LANGUAGE`, `PARCHA_TRANSLATION_TARGET_LANGUAGE`, `PARCHA_TTS_LANGUAGE`, `PARCHA_TTS_SPEAKER`, upload limits). Loads ROOT `.env` only.
- `app/core/db.py` — shared async Supabase client (pre-existing) + NEW `reset_client()` (test-only loop-rebinding escape).
- `app/core/money.py` — Decimal helpers: `q2` (2-dp HALF_UP), `dec` (float-safe via str), `as_float` (serialize to JSON number).
- `app/core/repo.py` — Module 2 invoice/supplier/SKU reads and invoice/line/IMS/loan persistence; Module 4 query packages contain their own read adapters over the shared Supabase client.
- `app/api/scan_router.py`, `resolve_router.py`, `export_router.py`, `demo_router.py`.
- `app/api/ws_router.py` + `app/core/ws_manager.py` — app-scoped connection registry, broadcast envelope, disconnect cleanup.
- `backend/static/crops/demo_pen_edit.jpg` — visibly labeled demo-only placeholder, not a Gemini crop. `backend/static/audio/demo_alert.wav` remains absent for the fixture path; live uploaded scans generate per-invoice WAVs when Sarvam is configured.
- `app/services/pipeline.py` — `LiveParchaPipeline` plus `FixturePipeline` reserved for `load-sample` only.
- `app/services/credit_rules.py` — transaction-backed CIS daily-credit cap with stored merchant-volume fallback.
- `app/credit/service/sweep_preview.py` — read-only Paytm balance/QR forecast and simulated bank-shortfall projection; never writes D2–D7 preview values.
- `app/services/merchant_resolver.py` — B1 demo-merchant chain.
- `app/services/exporters.py` — Tally XML + Marg CSV builders (Module 5 deliverable, gateway-exposed).
- `app/services/gemini_vision.py`, `pillow_cropper.py` — Module 3 vision extraction and contextual crop.
- `app/services/sarvam_tts.py` — Sarvam Bulbul v4 Flash WAV generation; optional-key/provider failure preserves browser speech fallback.
- `backend/scripts/sarvam_tts_smoke.py` — one-off real API smoke script; output WAV is locally ignored.
- `app/engine/` and `app/{bill_validation,price_analysis,credit}/` — Module 4 Decimal engines and read APIs.

## 3. Integration boundaries and remaining mock

- **Live scan pipeline:** `LiveParchaPipeline` uses Gemini 3.6 Flash, Pillow, `math_engine`, `waterfall_engine`, `LiveCreditRules`, Sarvam Bulbul TTS, and Supabase persistence. It preserves extracted quantities; no demo-specific `12 → 10` rewrite. Exact supplier/SKU matches only; unmatched references are not fabricated.
- **Voice alert:** `voice_transcript` is a concise deterministic three-sentence summary (supplier/invoice, flagged lines/reason/overcharge, payout/day-one split). Sarvam translates the deterministic transcript from the configured source language to the target language, then Bulbul v4 Flash synthesizes it with an explicit matching speaker. `PARCHA_TTS_LANGUAGE` must match `PARCHA_TRANSLATION_TARGET_LANGUAGE`; defaults are Hindi. Amount and invoice tokens are protected during translation. Translation failure retains the source transcript; synthesis failure retains localized text for browser fallback. Translation and TTS run sequentially with 5-second timeouts, so localization may exceed the 3.5-second scan target.
- **Amount rule:** accepted line totals use the invoice's billed rate with Gemini's accepted quantity; high rates are flagged but not auto-repriced. Overcharge is computed from positive line-level printed-vs-recomputed differences; the printed grand total is display-only and may contain freight.
- **Credit rule:** the CIS seven-day flow uses 30-day successful incoming QR transactions, with `avg_daily_qr_volume` fallback; daily cap is 35% of average daily QR volume. Resolve rejects an amount over the seven-day cap.
- **Loan playback:** resolve records Day 1 in `merchant_account_ledger` as signed `LOAN_DEDUCT`, consistent with the persisted `remaining_balance`. `GET /api/credit/{invoice_id}/sweep-preview` calculates Days 2–7 from current available Paytm balance (`OPENING + signed ledger + successful incoming QR transactions`) and recent QR receipts. If projected Paytm funds fall short, it shows a simulated bank-mandate shortfall; the GET does not mutate loan or ledger state. The drawer labels D2–D7 and bank fallback as preview only. The UI what-if trigger is balance insufficiency; the Blueprint's 48-hour zero-QR production trigger remains unchanged.
- **Remaining fixture:** `POST /api/demo/load-sample` intentionally returns the CIS golden fixture for the pitch fail-safe; it does not write DB rows or broadcast WS events.
- **Weekly credit:** Module 4 read-only GETs remain mounted. Its weekly-credit POST write routes are unmounted until the ledger kind contract is explicitly changed; no schema change was approved.

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
- ✅ Integrated host TestClient checked live Supabase read-only validation, price analysis, credit recommendation, and export; test-patched scan verified event order and REST/WS shape without calling Gemini or writing DB rows.
- ✅ All 34 unit tests pass, including Day 1 ledger consistency/retry handling, read-only QR/bank-shortfall projection, mocked TTS fallback, live-pipeline amount mapping, median benchmark, and disabled weekly-credit POST routes.
- ✅ Host TestClient resolve against the demo invoice wrote one Day 1 `LOAN_DEDUCT`; the read-only preview returned six days. The temporary loan/ledger row and invoice/IMS status changes were rolled back and verified against the exact pre-test state.
- ⏳ Live Sarvam smoke not completed: SDK installed locally, but the root `.env` has no key. Rotate the chat-exposed key and add its replacement to `.env`, then run `python scripts/sarvam_tts_smoke.py` from `backend/`.
- ⏳ Deferred (Docker Desktop unavailable): `docker compose up --build` health check + browser-through-proxy smoke for `/ws` and `/static`. Existing Compose mounts persist crops/audio; backend also mounts `./contracts:/contracts:ro` for the fixture.
- Live DB had one pre-existing non-seed loan + two related ledger rows before this slice's write-path check (57 loans / 177 ledger vs seed baseline 56 / 175). These were left untouched; temporary test resolve was rolled back and the demo invoice is AUDITED/ACCEPTED with no loan.

## 6. Remaining verification / future decisions

1. **Docker verification:** once Docker Desktop works, rebuild/test both services (the API image now needs `sarvamai`) and verify `/api`, `/ws`, and `/static` through the Angular 4200 proxy.
2. **Gemini end-to-end scan:** not run during merge checks (would call external Gemini and persist an invoice); test later with an approved bill/API key and clean up only the generated test rows.
3. **Frontend/Docker verification:** drawer playback is implemented but not browser-tested because Docker is unavailable. Rebuild the frontend/API images and verify the projected QR/bank path when Docker works.
4. **Resolve Event 3 / weekly-credit writes:** remain disabled until coordinating with Dev 1 and approving any needed ledger contract change.

## 7. Quick host-only API test (no Docker, no frontend)

From the repository root (requires the existing `.env` and backend Python dependencies):

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`. `/healthz`, `POST /api/demo/load-sample`, exports, and static URLs are easy read-only checks. `POST /api/parcha/scan` emits two WS events to a connected `/ws/counter` client; Swagger alone does not display them, so use a WS client (e.g. browser devtools/`websocat`) alongside the POST. **Resolve writes to live Supabase**; it is intentionally not a harmless read-only test. Stop uvicorn with Ctrl+C.
