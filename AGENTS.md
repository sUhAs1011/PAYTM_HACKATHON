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

- `docker compose up --build` is the intended local start command. It will not become healthy until an Angular workspace and `app.main:app` exist. `app.main` is a scaffold assumption, not a CIS path. The Angular workspace now exists and is Docker-verified.
- Until Module 2 lands `app.main:app`, verify the frontend alone: `docker compose up --build -d --no-deps frontend` (the api healthcheck gates the frontend `depends_on`, so `--no-deps` is required while the backend is a placeholder). Docker Desktop must be running first. Frontend serves at http://localhost:4200; phone uses the host LAN address on 4200.
- No lint or test command yet.

## Progress

- 2026-10-30: Source docs are in `documents/`. `README.md` is a title only. Application modules are empty placeholders, not implementations.
- 2026-10-30: Supabase org and project exist. The user was given a SQL Editor script for the seven tables, foreign keys, and HNSW index, plus a follow-up to enable RLS with no policies. Execution is not confirmed in this repo. Do not re-run DDL or drop tables unless the user asks.
- 2026-10-30: Demo seed was intentionally not applied. The seed in the engineering document attaches five Fortune Oil rows to one merchant invoice, which does not satisfy Mandi-Pulse.
- 2026-10-30: ED now specifies a Docker Compose frontend/API stack, external managed integrations, secure runtime secrets, static-asset persistence, and Docker-aware proxy routing.
- 2026-10-30: Repo scaffold exists: empty ED source files, empty SQL migrations, CIS `contracts/demo_bill_fixture.json`, `frontend/package.json` (Angular 19.2.15), `backend/requirements.txt`, Dockerfiles, ignore files, proxy configs, `compose.yaml`, and `.env.example`. No application logic and no DDL. `.gitkeep` files hold empty directories. `.gitignore` excludes `.env` and dependency folders. Env names in `.env.example` are placeholders, not a config contract.
- 2026-10-30: Module 1 (dual-surface client) implemented and Docker-verified. Angular 19.2.15 workspace hand-authored: `frontend/angular.json`, `tsconfig.json` (paths `@contracts/contracts` and `@contracts/demo-bill-fixture` → `../contracts/`), `tsconfig.app.json`, bootstrap files, routes `/scan` and `/counter`, components `soundbox-twin`/`audit-table`/`whatsapp-drawer`/`split-credit`, services `websocket`/`api`, `shared/format.ts`, `assets/mock/demo_pen_edit.svg`. `contracts/contracts.ts` populated from CIS §4/§5.
- 2026-10-30: Module 1 contract deltas and decisions. `AuditCompleteData` (WS Event 2) is the narrower type; `AuditedInvoiceResponse` (REST + fixture) adds `supplier_gstin`/`invoice_date` — the CIS Event 2 example omits them, documented in `contracts.ts`. `ResolveActionResponse` is modelled on `PAYOUT_APPROVED.data` because CIS never defines it — ASSUMPTION comment in `contracts.ts`, needs Dev 2 confirmation. Scan uploads use `DEMO_MERCHANT_ID` constant (seed merchant `a0000000-...-0001`) until an auth surface exists. Mock-first: when endpoints are unreachable, `api.service` falls back to `demo_bill_fixture.json` and `websocket.service` injects mock events through the same observables (one code path for mock and live); crop URL maps to the bundled SVG, audio falls back to `speechSynthesis` of `voice_transcript`. `frontend/package.json` gained `@angular-devkit/build-angular@19.2.15` (scaffold gap — `ng serve` cannot run without a builder package). `compose.yaml` frontend service mounts `./contracts:/contracts:ro` so the `../contracts` tsconfig paths resolve in-container (frontend build context excludes the repo root). `frontend/Dockerfile` pre-creates `.angular/cache` owned by `node` (Vite dep-optimizer was hitting EACCES under the non-root user).
- 2026-10-30: Module 1 verified through Docker: container healthy on 4200, `/counter` full demo flow (Load Demo Bill → fixture AUDIT_ALERT with red Fortune Oil row, yellow Parle-G 76% row, twin card, SHIELD_READY, crop card → Paytm Button → WhatsApp drawer + IMS "Shield Active · DISPUTED_PENDING_IMS" → 7-day split sheet: D1 ₹1,980 filled, remaining ₹11,880) and `/scan` (hidden `capture="environment"` input, fail-safe flow to summary card) all confirmed via in-app browser DOM checks. Remaining proxy errors (`ENOTFOUND api`) are the absent backend and disappear when Module 2 runs.
- 2026-10-30: Desktop-layout polish after user feedback: `/counter` shell widened to `max-width: 1720px` (98% viewport fill measured) and `/scan` gained a desktop hint linking to `/counter`, since the root redirect lands laptop users on the intentionally phone-narrow (480px) scan view. Remember: source is baked into the image — every frontend code change needs `docker compose up --build -d --no-deps frontend` (cached, ~30s); a plain restart serves stale code.
- 2026-10-31: Added `DEMO_REFERENCE_GUIDE.md` covering phone-and-laptop Wi-Fi/hotspot setup, URL endpoints, 4-state demo walkthrough, Docker commands, and pitch troubleshooting.
- 2026-10-31: Added `GEMINI_EXTRACTION_IMPLEMENTATION_GUIDE.md` specifying step-by-step code and execution details for Gemini 2.5 Flash VLM extraction, Pillow pen crop, and FastAPI/WebSocket frontend connection.
- 2026-10-31: Implemented Gemini 2.5 Flash vision extraction (`backend/app/services/gemini_vision.py`), 15% padded pen cropper (`backend/app/services/pillow_cropper.py`), shared Pydantic contracts (`contracts/contracts.py`), and minimal FastAPI gateway/WebSocket bridge (`backend/app/main.py`, `scan_router.py`, `resolve_router.py`, `ws_manager.py`) wired directly to the Angular frontend. `compose.yaml` updated to mount `contracts/` into the `api` service.
- 2026-10-31: Eliminated silent hardcoded fallback from `gemini_vision.py` and `scan_router.py`; moved `GEMINI_API_KEY` into root `.env` (sanitized `.env.example`); extraction now runs live through Gemini with dynamic totals and line items.
- 2026-10-31: Removed hardcoded `fallbackToDemo` from Angular `api.service.ts`; added direct "Upload Bill Photo" action on laptop `/counter` dashboard so users can upload bills directly on desktop; verified real crops pass through from `/static/crops/`.
- 2026-10-31: Fixed return type bug in `gemini_vision.py` (`response` -> `response.parsed`) which was throwing unhandled `AttributeError` and causing HTTP 500 on scan upload; added full defensive error logging in `scan_router.py`.
- 2026-10-31: Locked vision extractor strictly to `gemini-2.5-flash` in `gemini_vision.py` (removed fallback loop that was triggering 404 for `gemini-1.5-flash`); sanitized `.env` and `config.py` to strip literal quotes from the new `AQ.` auth key format.
- 2026-10-31: Redesigned Pillow cropper in `pillow_cropper.py` to capture full line-item row context (75% image width framing) and draw an AI highlight bounding box with 'PEN EDIT DETECTED' badge; updated frontend CSS to prevent crop ballooning.
- 2026-10-31: Fixed quantity OCR ambiguity (normalized strikethrough 12 to 10 for pen edit) and refined `SYSTEM_INSTRUCTION` in `gemini_vision.py`; implemented strict `billed_qty * unit_rate` decimal arithmetic and total summation in `scan_router.py`; prioritized truly modified line items for pen-dispute crop framing to eliminate false positive crop selections.
- 2026-10-31: Added `suhas.md` documenting the complete vision extraction & ingress implementation, data models, contracts, and integration points for teammates.

## Do not silently fix

These spec tensions are known. Flag them. Do not edit the source docs or invent schema to resolve them unless the user asks.

- `canonical_skus` in the engineering document is missing a comma before `aliases`. The runnable Supabase script added that comma. Column set is unchanged: `aliases text[]` is required.
- Enable `vector` in the `extensions` schema, as current Supabase docs require. If `vector` is not on `search_path`, qualify the type as `extensions.vector(768)` only. Do not rename `embedding`.
- Golden fixture daily cap is 3500 and max credit is 24500. Seed merchant `avg_daily_qr_volume` is 15000, which implies a 5250 cap. Do not pick a winner in code.
- GST fields use different vocabularies on purpose: `gst_ims_records.ims_status` is `PENDING | ACCEPTED | REJECTED`; `invoices.status` includes `DISPUTED_PENDING_IMS`; the audit payload uses `gst_ims_shield.status = SHIELD_READY`. Map them. Do not collapse them.
- Tables created through the SQL Editor do not get row level security. The Data API publishable key must not be able to read these financial tables. Backend access later should use the secret key, which bypasses RLS.

## Security

- Financial tables are backend-owned. Do not add anon or authenticated Data API policies unless the user asks.
- Dispute crops and TTS audio are local `/static` files in the spec, not Supabase Storage, until the spec changes.
- GST IMS is a staging queue and export, not a live GSTN write.
