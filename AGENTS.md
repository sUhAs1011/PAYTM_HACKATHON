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
- Module 4 is assigned to the current user. Other module ownership remains unassigned; do not start another module until the user names it and approves a plan.
- No multi-file implementation until a 4-part plan is approved: Scope and Non-Goals, Contract References, Step-by-Step Tasks, Definition of Done.
- Never put API keys, database URLs, or service-role keys in the repo.

## Architecture

Five modules. Stay inside the assigned boundary.

| Module | Owner | Owns |
| --- | --- | --- |
| 1 Dual-surface client | Dev 1 | Angular 19 `/scan` and `/counter`, Soundbox twin, drawers |
| 2 API gateway and realtime | Dev 2 | FastAPI REST, `/ws/counter`, `/static` |
| 3 Vision and voice | Dev 3 | Gemini extraction, Pillow crop, embeddings, Sarvam TTS |
| 4 Deterministic audit | Current user | Decimal bill validation, supplier/pincode price analysis, weekly split-credit simulation |
| 5 Persistence | Dev 2 | Supabase schema, seed, Tally XML / Marg CSV export |

The root layout is scaffolded: `compose.yaml`, `.dockerignore`, `.env.example`, `contracts/`, `frontend/`, `backend/`, and `supabase/migrations/`. Module 4 packages are under `backend/app/{bill_validation,price_analysis,credit}/`, with pure financial functions under `backend/app/engine/`.

Camera capture is a hidden file input with `capture="environment"` and `accept="image/*"`. Do not use `getUserMedia`. Proxy `/api`, `/static`, and `/ws` through the Angular dev server on port 4200. In Compose, proxy to `http://api:8000` / `ws://api:8000`, not container-local `localhost`.

## Immutable contracts

Do not rename columns, routes, event names, or payload keys. Casing in the spec wins.

- `POST /api/parcha/scan`
- `POST /api/parcha/{id}/resolve` with `{"action": "APPROVE_SPLIT", "tenure_days": 7}`
- `GET /api/parcha/{id}/export?format=tally|marg`
- `POST /api/demo/load-sample`
- WebSocket `/ws/counter`: `SCAN_STARTED`, `AUDIT_COMPLETE`, `PAYOUT_APPROVED`
- Tables: `merchants`, `suppliers`, `canonical_skus`, `invoices`, `invoice_line_items`, `gst_ims_records`, `split_credit_loans`
- Module 4 also references the existing `transactions` and `merchant_account_ledger` tables shown in the user's Supabase schema. Do not create or alter tables/columns for Module 4 without explicit approval.
- Cosine SKU search uses `<=>` and HNSW index `idx_canonical_skus_embedding` on `embedding vector(768)`

Gemini extracts numbers and boxes only. All totals, tax, landed cost, and loan math use Python `decimal.Decimal`.

True landed unit cost is `(net line amount + GST) / (billed qty + free qty)`.

The CIS resolve-flow lending cap is 35% of the merchant's 30-day average daily QR volume. The additive Module 4 weekly-credit API uses a weekly EMI cap of 35% of average weekly incoming QR earnings. Mandi-Pulse runs only when at least 5 distinct stores have that canonical SKU in the pin code over 14 days. OCR confidence below 0.80 is a yellow review, not an auto-approve.

`APPROVE_SPLIT` is the only resolve action in the spec. It is expected to send the WhatsApp reconciliation preview, set GST IMS to disputed/pending, and create the loan schedule. Do not add a second resolve endpoint unless the user changes the spec.

## Commands

Do not run `npm install` or `pip install` unless the user asks.

- DB smoke check passed 2026-10-30: from `backend/`, `python -m app.core.db` loads `.env`, verifies the key type, and prints row counts for all 7 CIS tables (zeros until the seed is applied). Exits non-zero on any failure.
- Module 4 offline tests: from `backend/`, `python -m unittest discover -s tests -v`.
- API start: from `backend/`, `uvicorn app.main:app --env-file ../.env --host 0.0.0.0 --port 8000`. Routes require root `.env` with Supabase credentials.
- Logging: `backend/app/core/logging_config.py` configures stdout logs and request IDs; set `LOG_LEVEL=DEBUG` for query row counts. Do not log invoice payloads, transaction amounts, phone/VPA values, or credentials.
- `docker compose up --build` remains the intended local stack command; frontend route work is still pending.

## Progress

- 2026-10-30: Supabase client verified end-to-end: `python -m app.core.db` from `backend/` reaches all 7 CIS tables (0 rows each). `sb_secret_` key is valid; SUPABASE_URL `nccjpyidbbfjmflifalp.supabase.co`. DDL in Supabase is confirmed executed (tables resolve; no PGRST205).
- 2026-10-30: supabase-py upgraded 2.11.0 → 2.33.0 via `pip install --user`. Versions up to ~2.11 abort with `SupabaseException: Invalid API key` because they regex-check the key as a JWT; `sb_secret_` keys have no dots and fail that check before any network call. Do not downgrade.
- 2026-10-30: Source docs are in `documents/`. `README.md` is a title only. Module 4 implementation is documented in `soumya.md`; remaining modules may still be placeholders.
- 2026-10-30: Supabase org and project exist. The SQL Editor DDL script (seven tables, foreign keys, HNSW index, RLS with no policies) is confirmed applied 2026-10-30 — all 7 tables resolve via the smoke check. Do not re-run DDL or drop tables unless the user asks.
- 2026-10-30: Demo seed was intentionally not applied. The seed in the engineering document attaches five Fortune Oil rows to one merchant invoice, which does not satisfy Mandi-Pulse.
- 2026-10-30: ED now specifies a Docker Compose frontend/API stack, external managed integrations, secure runtime secrets, static-asset persistence, and Docker-aware proxy routing.
- 2026-10-30: Repo scaffold includes CIS contracts/fixture, frontend package manifest, backend requirements, Dockerfiles, proxy configs, Compose, and empty migration placeholders. Module 4 adds APIs over existing Supabase tables; no schema migration or seed is part of this module.
- 2026-10-30: Module 4 uses `invoices` + `invoice_line_items` + `merchants` + `suppliers` for validation and price analysis; `transactions` for incoming QR history; `split_credit_loans` + `merchant_account_ledger` for simulated weekly installments. Weekly terms use existing loan columns (`tenure_days = weeks × 7`) without changing the CIS schema. The live ledger unique constraint `uq_ledger_loan_day` permits one row per loan/local day, so each weekly cycle must write one combined paid/missed/partial event. The simulated-disbursement ledger marker distinguishes these weekly loans from legacy daily CIS loans. Missed-installment ledger events are simulation alerts, not actual autopay withdrawals.
- 2026-10-30: Module 4 logging uses `logging_config.py` stdout setup and request IDs, with controller/service lifecycle logs and debug-level Supabase row counts. Sensitive invoice, payer, VPA, phone, and credential values are intentionally excluded.
- 2026-10-30: `backend/app/core/db.py` implemented: shared async Supabase client via `await create_async_client(url, key)`. The factory is a coroutine in supabase-py 2.x — must be awaited. Uses the service_role secret key (bypasses RLS). No db name/password needed; PostgREST over HTTPS. `SUPABASE_URL` and `SUPABASE_SECRET_KEY` are now a real config contract; GEMINI/SARVAM names are still placeholders. `python-dotenv` added to requirements (loaded only in the `__main__` block; importing db.py has no side effects). The check loads the repo-root `.env` by explicit path (`parents[3]` of db.py); never put a `.env` in a subfolder — it would shadow the root one. Missing-env and bad-key paths raise clear errors.

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
