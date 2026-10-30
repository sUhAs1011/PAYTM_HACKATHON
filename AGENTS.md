# ParchaPay AI

Agent instructions for this repo. OpenCode loads this file automatically. Do not duplicate it into `CLAUDE.md`.

ParchaPay AI is a Paytm Build for India 2026 Track 1 demo: a merchant photographs a wholesale bill, a vision model extracts it, deterministic Python checks the math and local prices, and a Soundbox digital twin speaks the audit, then triggers a supplier reconciliation note and a 7-day QR split-credit.

## Keep this file current

This file is living agent context, not a changelog dump.

After any change to a doc or code file in this repo, update this file in the same change. Record only what a future agent needs: new paths, commands, decisions, contract deltas, and status. Do not paste file contents, secrets, or a line-by-line history. If the change does not affect how an agent should work, add one line under Progress and leave the rest alone.

User chat overrides this file. The nearest `AGENTS.md` wins over this root file once nested module files exist. Do not add those until a module directory exists.

## Read before you edit

OpenCode does not auto-load `@` references. Use the Read tool, and only the file the task needs.

- Product and demo intent: `documents/ParchaPay AI Blueprint.md`
- P0/P1 scope and journey: `documents/ParchaPay AI - Product Requirements Document (PRD).md`
- Architecture, DDL, Pydantic, REST, and WebSocket contracts: `documents/engineering_document_core_interoperability_specification-2.md`

For any API, schema, event, or column work, read the Core Interoperability Specification in that engineering document before writing code. Do not invent endpoints or rename fields to paper over gaps.

## Locked decisions

- App code lives at the repo root. Do not create a nested `parchapay-ai/` directory. The engineering document's tree is the module layout, not a parent folder.
- Runtime is live Supabase Postgres + pgvector, Gemini 2.5 Flash, and Sarvam Bulbul TTS. No SQLite stand-in. Mock fixtures are for isolated UI and pipeline tests, not the final data store.
- Dockerize from the start: root `compose.yaml` runs separate `frontend` and `api` services; Supabase/Gemini/Sarvam stay managed external services. Use the Docker proxy target `api:8000`, per-build-context ignore files, backend-only runtime secrets, and a volume for generated `/static` crops/audio.
- Module ownership is not assigned yet. Do not start a module until the user names it and approves a plan.
- No multi-file implementation until a 4-part plan is approved: Scope and Non-Goals, Contract References, Step-by-Step Tasks, Definition of Done.
- Never put API keys, database URLs, or service-role keys in the repo.
- All runs and tests go through Docker (user directive, 2026-10-30). Installs happen inside image builds; host `npm install`/`ng serve` is not the verification path.

## Architecture

Five modules. Stay inside the assigned boundary.

| Module | Owner | Owns |
| --- | --- | --- |
| 1 Dual-surface client | Dev 1 | Angular 19 `/scan` and `/counter`, Soundbox twin, drawers |
| 2 API gateway and realtime | Dev 2 | FastAPI REST, `/ws/counter`, `/static` |
| 3 Vision and voice | Dev 3 | Gemini extraction, Pillow crop, embeddings, Sarvam TTS |
| 4 Deterministic audit | Dev 3 | Decimal math, price waterfall, split-credit schedule |
| 5 Persistence | Dev 2 | Supabase schema, seed, Tally XML / Marg CSV export |

Planned root layout, not created yet: `compose.yaml`, `.dockerignore`, `.env.example`, `contracts/`, `frontend/` (with `Dockerfile`, `Dockerfile.dockerignore`, `proxy.conf.json`, and `proxy.docker.conf.json`), `backend/` (with `Dockerfile` and `Dockerfile.dockerignore`), `supabase/migrations/`.

Camera capture is a hidden file input with `capture="environment"` and `accept="image/*"`. Do not use `getUserMedia`. Proxy `/api`, `/static`, and `/ws` through the Angular dev server on port 4200. In Compose, proxy to `http://api:8000` / `ws://api:8000`, not container-local `localhost`.

## Immutable contracts

Do not rename columns, routes, event names, or payload keys. Casing in the spec wins.

- `POST /api/parcha/scan`
- `POST /api/parcha/{id}/resolve` with `{"action": "APPROVE_SPLIT", "tenure_days": 7}`
- `GET /api/parcha/{id}/export?format=tally|marg`
- `POST /api/demo/load-sample`
- WebSocket `/ws/counter`: `SCAN_STARTED`, `AUDIT_COMPLETE`, `PAYOUT_APPROVED`
- Tables: `merchants`, `suppliers`, `canonical_skus`, `invoices`, `invoice_line_items`, `gst_ims_records`, `split_credit_loans`
- Cosine SKU search uses `<=>` and HNSW index `idx_canonical_skus_embedding` on `embedding vector(768)`

Gemini extracts numbers and boxes only. All totals, tax, landed cost, and loan math use Python `decimal.Decimal`.

True landed unit cost is `(net line amount + GST) / (billed qty + free qty)`.

Lending cap is 35% of the merchant's 30-day average daily QR volume. Mandi-Pulse runs only when at least 5 distinct stores have that canonical SKU in the pin code over 14 days. OCR confidence below 0.80 is a yellow review, not an auto-approve.

`APPROVE_SPLIT` is the only resolve action in the spec. It is expected to send the WhatsApp reconciliation preview, set GST IMS to disputed/pending, and create the loan schedule. Do not add a second resolve endpoint unless the user changes the spec.

## Commands

Scaffold only. Do not run `npm install` or `pip install` unless the user asks.

- DB smoke check passed 2026-10-31 with seed applied: from `backend/`, `python -m app.core.db` loads `.env`, verifies the key type, and prints row counts for all 9 tables — the 7 CIS tables plus the 2 user-approved auxiliaries (`transactions`, `merchant_account_ledger`). Expected seeded counts: 30/8/20/150/502/150/56 CIS + 7,233/175 aux. Exits non-zero on any failure.
- All 9 tables are seeded and verified 2026-10-31 (the ED's own five-row seed was not used; see Progress).
- `docker compose up --build` is the intended local start command — both services should become fully healthy now (`backend/app/main.py` exists). NOT YET Docker-verified: Docker Desktop was broken on the user's laptop 2026-10-31; verification was done via a host-run Starlette TestClient instead (user-approved exception; see Progress). When Docker Desktop works, confirm: both containers healthy, frontend proxy reaches the real API (at least one `/api/demo/load-sample` request from the browser through 4200). Frontend serves at http://localhost:4200; phone uses the host LAN address on 4200. Docker Desktop must be running first.
- User-approved Docker-unavailable API smoke path (no frontend): from `backend/`, run `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`; Swagger at `http://127.0.0.1:8000/docs`; stop with Ctrl+C. This is a temporary host verification exception, not a substitute for pending Compose verification.
- No lint or test command yet.

## Progress

- 2026-10-31: `merchant_account_ledger` DDL designed with user (approved deviation #2): signed amounts, kind ('OPENING'|'LOAN_DEDUCT'|'QR_CREDIT'|'REFUND'), nullable loan_id FK, unique (loan_id, IST-day) partial index — the first `timestamptz::date` index attempt failed 42P17; the immutable fix is `(entry_ts at time zone 'Asia/Kolkata')::date`. Seed data: `merchant_account_ledger.csv` + `synthetic_seed_ledger.sql` (175 rows, ~30 KB, idempotent). Ledger invariant: for 54/56 loans, principal − ΣLOAN_DEDUCT == split_credit_loans.remaining_balance; the 2 exceptions are loans created Oct 28 whose required deduction days exceed the Oct-only window (documented, not an error). QR credits deliberately NOT duplicated into the ledger — they derive from `transactions` (SUCCESS); balance = Σ OPENING + Σ ledger + Σ transactions.
- 2026-10-31: Supabase SQL Editor rejects the 1.9 MB full seed ("Query is too large"). Load order: `synthetic_seed.sql` (7 CIS tables, ~458 KB) → user's `transactions` DDL → `synthetic_seed_transactions_1..4.sql` (4 files, ~368 KB, 1,809/1,809/1,809/1,806 rows) → `synthetic_seed_ledger.sql`. All idempotent via ON CONFLICT; the generation invariant (per-merchant SUCCESS sum == 30 x avg_daily_qr_volume) is verified against the CSV. Known demo tension: seeded `billed_total` includes charges that are not line items (freight etc.) — Module 4 must derive totals/overcharge from line items, never the stored column.
- 2026-10-30: Transactions table approved as a deviation from the 7-table CIS (user-owned schema decision): t_id, merchant_id FK, amount, payer_vpa, merchant_vpa, txn_ref unique, txn_status, upi_partner, created_at + (merchant_id, created_at) index. `transactions.csv` (7,233 rows, 2026-10-01..10-30) + append-only block at the end of `parchapay_synthetic_dataset/synthetic_seed.sql` are data-only; the table DDL must exist in Supabase first (user creates it). Invariant enforced by generation rule: per merchant, SUCCESS amounts sum to exactly 30 x avg_daily_qr_volume, so the computed 30-day average equals the stored column — seeding must never violate this, or Module 4's 35% cap has two disagreeing sources.
- 2026-10-30: Supabase client verified end-to-end: `python -m app.core.db` from `backend/` reaches all 7 CIS tables (0 rows each). `sb_secret_` key is valid; SUPABASE_URL `nccjpyidbbfjmflifalp.supabase.co`. DDL in Supabase is confirmed executed (tables resolve; no PGRST205).
- 2026-10-30: supabase-py upgraded 2.11.0 → 2.33.0 via `pip install --user`. Versions up to ~2.11 abort with `SupabaseException: Invalid API key` because they regex-check the key as a JWT; `sb_secret_` keys have no dots and fail that check before any network call. Do not downgrade.
- 2026-10-30: Source docs are in `documents/`. `README.md` is a title only. Application modules are empty placeholders, not implementations.
- 2026-10-30: Supabase org and project exist. The SQL Editor DDL script (seven tables, foreign keys, HNSW index, RLS with no policies) is confirmed applied 2026-10-30 — all 7 tables resolve via the smoke check. Do not re-run DDL or drop tables unless the user asks.
- 2026-10-30: Demo seed decision: the ED's own seed attaches five Fortune Oil rows to one merchant invoice, which does not satisfy Mandi-Pulse, so it was never applied. Superseded 2026-10-31: the synthetic dataset seed IS applied — all 9 tables seeded and verified (30/8/20/150/502/150/56 CIS + 7,233 transactions + 175 ledger).
- 2026-10-30: ED now specifies a Docker Compose frontend/API stack, external managed integrations, secure runtime secrets, static-asset persistence, and Docker-aware proxy routing.
- 2026-10-30: Repo scaffold exists: empty ED source files, empty SQL migrations, CIS `contracts/demo_bill_fixture.json`, `frontend/package.json` (Angular 19.2.15), `backend/requirements.txt`, Dockerfiles, ignore files, proxy configs, `compose.yaml`, and `.env.example`. No application logic and no DDL. `.gitkeep` files hold empty directories. `.gitignore` excludes `.env` and dependency folders.
- 2026-10-30: `backend/app/core/db.py` implemented: shared async Supabase client via `await create_async_client(url, key)`. The factory is a coroutine in supabase-py 2.x — must be awaited. Uses the service_role secret key (bypasses RLS). No db name/password needed; PostgREST over HTTPS. `SUPABASE_URL` and `SUPABASE_SECRET_KEY` are now a real config contract; GEMINI/SARVAM names are still placeholders. `python-dotenv` added to requirements (loaded only in the `__main__` block; importing db.py has no side effects). The check loads the repo-root `.env` by explicit path (`parents[3]` of db.py); never put a `.env` in a subfolder — it would shadow the root one. Missing-env and bad-key paths raise clear errors.
- 2026-10-30: Module 1 (dual-surface client) implemented and Docker-verified. Angular 19.2.15 workspace hand-authored: `frontend/angular.json`, `tsconfig.json` (paths `@contracts/contracts` and `@contracts/demo-bill-fixture` → `../contracts/`), `tsconfig.app.json`, bootstrap files, routes `/scan` and `/counter`, components `soundbox-twin`/`audit-table`/`whatsapp-drawer`/`split-credit`, services `websocket`/`api`, `shared/format.ts`, `assets/mock/demo_pen_edit.svg`. `contracts/contracts.ts` populated from CIS §4/§5.
- 2026-10-30: Module 1 contract deltas and decisions. `AuditCompleteData` (WS Event 2) is the narrower type; `AuditedInvoiceResponse` (REST + fixture) adds `supplier_gstin`/`invoice_date` — the CIS Event 2 example omits them, documented in `contracts.ts`. `ResolveActionResponse` is modelled on `PAYOUT_APPROVED.data` because CIS never defines it — ASSUMPTION comment in `contracts.ts`, needs Dev 2 confirmation. Scan uploads use `DEMO_MERCHANT_ID` constant (seed merchant `a0000000-...-0001`) until an auth surface exists. Mock-first: when endpoints are unreachable, `api.service` falls back to `demo_bill_fixture.json` and `websocket.service` injects mock events through the same observables (one code path for mock and live); crop URL maps to the bundled SVG, audio falls back to `speechSynthesis` of `voice_transcript`. `frontend/package.json` gained `@angular-devkit/build-angular@19.2.15` (scaffold gap — `ng serve` cannot run without a builder package). `compose.yaml` frontend service mounts `./contracts:/contracts:ro` so the `../contracts` tsconfig paths resolve in-container (frontend build context excludes the repo root). `frontend/Dockerfile` pre-creates `.angular/cache` owned by `node` (Vite dep-optimizer was hitting EACCES under the non-root user).
- 2026-10-30: Module 1 verified through Docker: container healthy on 4200, `/counter` full demo flow (Load Demo Bill → fixture AUDIT_ALERT with red Fortune Oil row, yellow Parle-G 76% row, twin card, SHIELD_READY, crop card → Paytm Button → WhatsApp drawer + IMS "Shield Active · DISPUTED_PENDING_IMS" → 7-day split sheet: D1 ₹1,980 filled, remaining ₹11,880) and `/scan` (hidden `capture="environment"` input, fail-safe flow to summary card) all confirmed via in-app browser DOM checks. Remaining proxy errors (`ENOTFOUND api`) are the absent backend and disappear when Module 2 runs.
- 2026-10-30: Desktop-layout polish after user feedback: `/counter` shell widened to `max-width: 1720px` (98% viewport fill measured) and `/scan` gained a desktop hint linking to `/counter`, since the root redirect lands laptop users on the intentionally phone-narrow (480px) scan view. Remember: source is baked into the image — every frontend code change needs `docker compose up --build -d --no-deps frontend` (cached, ~30s); a plain restart serves stale code.
- 2026-10-31: Module 2 slice 1 implemented — REST gateway only (plan: `.opencode/plans/module2-rest-api-plan.md`, approved). `backend/app/main.py` (`app.main:app`, `/healthz`, lifespan-wired seams) + routers `scan/resolve/export/demo` + `contracts.py` (Pydantic mirror of contracts.ts/CIS §5, field-casing immutable) + `core/{config,money,repo}.py` + seams `services/{pipeline,credit_rules,merchant_resolver,exporters}.py`. All 4 CIS endpoints verified live against seeded Supabase via TestClient: scan (fixture pipeline, multipart 422/413 guards, B1 merchant chain), load-sample (fixture verbatim + 404), export (Tally XML/Marg CSV from line items, 404 guards), resolve (200 → DB writes → 409 on repeat, 422 wrong action). Resolve writes verified exact (Decimal): loan principal 4935.06 / daily 705.01 / cap 2676.80 / remaining 4230.05, IMS upsert, status DISPUTED_PENDING_IMS; DB fully restored to pre-demo state after (56/150/AUDITED). Real pipeline did one full resolve against `d7b23a11-...` then rollback — DB pristine for the demo. Deferred to Docker working: compose health verification + browser-through-proxy checks.
- 2026-10-31: B1 resolved server-side (no frontend change): `resolve_merchant()` chain = exact merchants lookup → `PARCHA_DEMO_MERCHANT_ID` env → first seeded merchant with an invoice. Env set to `893054e0-9d6a-5a7c-955f-a36201ce39e6` (Sharma Kirana Store 11, pin 560103, avgQR 7648 → cap 2676.80): chosen because it owns RATE_HIKE-bearing invoice history AND exactly one clean resolve target (`d7b23a11-bf76-55dc-80b3-e027c52931d9`, INV-2026-0051, AUDITED + loan-free). Frontend `DEMO_MERCHANT_ID` constant stays as-is. User's scan-event rule: only actual scan uploads broadcast; `/api/demo/load-sample` does not.
- 2026-10-31: User-approved Module 2 WS/static policy (plan: `.opencode/plans/module2-websocket-static-plan.md`): scan uploads broadcast `SCAN_STARTED` + `AUDIT_COMPLETE`; load-sample and resolve are REST-only. Resolve's `PAYOUT_APPROVED` broadcast is intentionally withheld to avoid the frontend applying both REST + WS; this is an explicit deviation from CIS §4 Event 3, not a spec rewrite. Static fixture: labeled crop JPEG at `/static/crops/demo_pen_edit.jpg`; `/static/audio/demo_alert.wav` intentionally absent so the frontend's tap-to-speak transcript fallback works. Real Module 3 assets supersede fixture crop/audio URLs later.
- 2026-10-31: Module 2 WS/static implementation (plan: `.opencode/plans/module2-websocket-static-plan.md`): app-scoped `WebSocketManager`, exact `/ws/counter`, scan `SCAN_STARTED` before DB/pipeline and narrower `AUDIT_COMPLETE` after success, plus `/static` from persistent `backend/static/`. Host TestClient verified two-client broadcast, reconnect/disconnect cleanup, event ordering/envelope and REST-vs-WS shape; load-sample and resolve produced no queued events; invalid scan emitted none. Labeled fixture JPEG serves as `image/jpeg`; missing WAV and unknown assets return 404. No schema/frontend changes; Docker/proxy verification remains deferred. At the start of these tests, live DB already had one unseeded loan (`72a4e66f-...`) plus two related ledger rows (57 loans/177 ledger vs seed baseline 56/175); these were observed read-only and left untouched. Resolve test returned DB exactly to its pre-test state; demo target remains AUDITED/ACCEPTED with no loan.
- 2026-10-31: Resolve IMS handling changed from insert to UPSERT discovered at implementation: every seeded invoice already has exactly 1 `gst_ims_records` row, so resolve updates existing row's `ims_status` → PENDING (or inserts if absent), keeping 1-row-per-invoice. Provisional seams: `FixturePipeline` (scan returns CIS §5 golden fixture, ZERO DB writes) and `ProvisionalCreditRules` (cap = 0.35 × stored avg_daily_qr_volume, matching seed invariants; NOT recomputed from transactions). Module 3/4 replace them via `set_pipeline()` / `set_credit_rules()` — zero gateway changes at integration. compose.yaml api service now mounts `./contracts:/contracts:ro` (fixture path for load-sample/scan); `.env.example` gained `PARCHA_DEMO_MERCHANT_ID` + optional `PARCHA_FIXTURE_PATH`. `db.reset_client()` added (loop-rebinding escape for test contexts only). Module 4 computes the 14-day median band per canonical SKU + pin code from `invoice_line_items ⋈ invoices ⋈ merchants` at audit time — NO new table, `mandi_pulse_observations.csv` stays a repo-side verification fixture only (not seeded; verified to match recomputed medians in 437/502 line items, ~₹1 in the rest). The ≥5-distinct-stores gate is likewise evaluated from invoice history. The last open data-layer question is closed; nothing further to seed.
- 2026-10-31: Added `DEMO_REFERENCE_GUIDE.md` covering phone-and-laptop Wi-Fi/hotspot setup, URL endpoints, 4-state demo walkthrough, Docker commands, and pitch troubleshooting.

## Do not silently fix

These spec tensions are known. Flag them. Do not edit the source docs or invent schema to resolve them unless the user asks.

- `canonical_skus` in the engineering document is missing a comma before `aliases`. The runnable Supabase script added that comma. Column set is unchanged: `aliases text[]` is required.
- Enable `vector` in the `extensions` schema, as current Supabase docs require. If `vector` is not on `search_path`, qualify the type as `extensions.vector(768)` only. Do not rename `embedding`.
- Golden fixture daily cap is 3500 and max credit is 24500. Seed merchant `avg_daily_qr_volume` is 15000, which implies a 5250 cap. Do not pick a winner in code.
- Module 1's `DEMO_MERCHANT_ID` constant is the ED seed merchant `a0000000-...-0001`, which does not exist in the applied synthetic dataset (real UUIDs). Until an auth surface exists, Module 2 must map the demo scan to a real seeded merchant (or the constant must be updated to one) so the 35% cap and engine math hit real rows. Confirm with Dev 1 before wiring.
- GST fields use different vocabularies on purpose: `gst_ims_records.ims_status` is `PENDING | ACCEPTED | REJECTED`; `invoices.status` includes `DISPUTED_PENDING_IMS`; the audit payload uses `gst_ims_shield.status = SHIELD_READY`. Map them. Do not collapse them.
- Tables created through the SQL Editor do not get row level security. The Data API publishable key must not be able to read these financial tables. Backend access later should use the secret key, which bypasses RLS.

## Security

- Financial tables are backend-owned. Do not add anon or authenticated Data API policies unless the user asks.
- Dispute crops and TTS audio are local `/static` files in the spec, not Supabase Storage, until the spec changes.
- GST IMS is a staging queue and export, not a live GSTN write.
