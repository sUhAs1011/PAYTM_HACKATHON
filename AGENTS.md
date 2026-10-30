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

- `docker compose up --build` is the intended local start command. It will not become healthy until an Angular workspace and `app.main:app` exist. `app.main` is a scaffold assumption, not a CIS path.
- No lint or test command yet.

## Progress

- 2026-10-30: Source docs are in `documents/`. `README.md` is a title only. Application modules are empty placeholders, not implementations.
- 2026-10-30: Supabase org and project exist. The user was given a SQL Editor script for the seven tables, foreign keys, and HNSW index, plus a follow-up to enable RLS with no policies. Execution is not confirmed in this repo. Do not re-run DDL or drop tables unless the user asks.
- 2026-10-30: Demo seed was intentionally not applied. The seed in the engineering document attaches five Fortune Oil rows to one merchant invoice, which does not satisfy Mandi-Pulse.
- 2026-10-30: ED now specifies a Docker Compose frontend/API stack, external managed integrations, secure runtime secrets, static-asset persistence, and Docker-aware proxy routing.
- 2026-10-30: Repo scaffold exists: empty ED source files, empty SQL migrations, CIS `contracts/demo_bill_fixture.json`, `frontend/package.json` (Angular 19.2.15), `backend/requirements.txt`, Dockerfiles, ignore files, proxy configs, `compose.yaml`, and `.env.example`. No application logic and no DDL. `.gitkeep` files hold empty directories. `.gitignore` excludes `.env` and dependency folders. Env names in `.env.example` are placeholders, not a config contract.

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
