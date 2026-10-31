# Render Free Demo Deployment + Basic Auth Plan

**Date:** 2026-10-31 · **Status:** approved; implementation complete locally, Render deployment pending · **Scope:** public hackathon demo only

## 1. Scope & Non-Goals

### Scope
- Deploy one production Docker web service on Render's Free plan, with the Angular production build served by FastAPI from the same origin. This keeps the existing relative `/api`, `/static`, and `/ws` URLs working without CORS or a second public service.
- Add optional HTTP Basic Auth for the billable/mutating operations: `POST /api/parcha/scan`, `POST /api/parcha/{invoice_id}/resolve`, and `POST /api/demo/load-sample` (the sample can make paid Sarvam calls too). Keep the local Compose workflow unauthenticated by default; require credentials when auth is enabled, and fail closed if the enabled deployment has no username/password.
- Have the browser collect the demo username/password in a small password dialog on the first protected action, send the Basic `Authorization` header over HTTPS, and retain it only for the current tab session. Never bake credentials into Angular assets, `render.yaml`, or the repo.
- Add a Render Blueprint and a Render-specific multi-stage Dockerfile. Keep Supabase, Gemini, and Sarvam managed external services; store their settings and Basic Auth credentials in Render's service environment.
- Keep `/healthz` unauthenticated for Render probes. Bundle `contracts/` and required golden static fixtures into the image because Render does not apply Compose bind mounts.

### Non-Goals / limitations
- No DB/schema, endpoint, request/response, WebSocket-event, or finance-rule changes. Basic Auth is a transport-level requirement on the existing POSTs.
- This is a demo access gate, not account-level authorization. Read-only APIs and `/ws/counter` remain public in this quick plan; keep demo data synthetic and do not upload real merchant invoices. Protecting WebSocket/read routes would require a broader auth flow.
- Do not add Render Postgres or persist generated `/static` audio/crops. Supabase remains the persistent store; generated assets may disappear when Render's free instance sleeps/restarts.
- No paid Render resources, no real provider calls as part of build/tests, and no credentials in Git. Gemini/Sarvam calls themselves may still incur provider charges.

## 2. Contract References

- CIS §4 routes remain unchanged: `POST /api/parcha/scan`, `POST /api/parcha/{id}/resolve`, `POST /api/demo/load-sample`, `/ws/counter`, and `/static`.
- Health check remains `GET /healthz`; configure it as the Render HTTP health-check path.
- Render docs checked 2026-10-31:
  - [Docker deploys](https://render.com/docs/docker)
  - [Web services and `PORT` binding](https://render.com/docs/web-services)
  - [Health checks](https://render.com/docs/health-checks)
  - [Blueprint YAML](https://render.com/docs/blueprint-spec)
  - [Environment variables/secrets](https://render.com/docs/configure-environment-variables)
  - [WebSockets](https://render.com/docs/websocket)
  - [Free-plan limits](https://render.com/docs/free)
- Render Free web services sleep after 15 minutes without inbound traffic, take about one minute to wake, have 0.1 CPU / 512 MB RAM, and have ephemeral filesystems. Plan for cold starts; do not rely on generated audio/crops surviving a sleep or deploy.

## 3. Step-by-Step Tasks

1. **Add opt-in backend Basic Auth.**
   - Add `PARCHA_DEMO_AUTH_ENABLED`, `PARCHA_DEMO_AUTH_USERNAME`, and `PARCHA_DEMO_AUTH_PASSWORD` runtime settings. Default auth off for current local Compose; Render enables it and supplies credentials out-of-band.
   - Implement a reusable FastAPI `HTTPBasic` dependency using `secrets.compare_digest`; return `401` plus `WWW-Authenticate: Basic` for missing/wrong credentials. If auth is enabled but credentials are empty, fail startup or fail closed.
   - Attach the dependency to scan, resolve, and load-sample only. Keep `/healthz` public for Render probes and preserve all route/payload contracts.

2. **Add minimal browser credential entry.**
   - Add one reusable username/password dialog for `/scan` and `/counter`; ask once when a protected request is needed, then retry that request with `Authorization: Basic ...`.
   - Store the credential only in `sessionStorage` for the open tab; clear it on a subsequent `401`. Never include it in URLs, logs, source, or build-time frontend variables.
   - Ensure the same `ApiService` path covers laptop upload, phone upload, resolve, and sample loading. Requests with no authorization header continue to work locally while auth is disabled.

3. **Package the production app as one Render container.**
   - Add a root-context, multi-stage Render Dockerfile: build Angular with Node in production mode, then install/run FastAPI from the Python image; copy the Angular `dist` output, `backend/`, `contracts/`, and the fixture crop needed by the demo.
   - Keep `.env` excluded from the build context. Adjust static-file ignore rules only as needed to retain committed demo fixtures while excluding generated `alert_*.wav` and `pen_edit_*.jpg` files.
   - Serve Angular `index.html` for `/`, `/scan`, and `/counter` after registering API, WebSocket, `/static`, and `/healthz` routes. Preserve the existing same-origin relative API and WebSocket URLs.
   - Make Uvicorn bind to `0.0.0.0:${PORT:-8000}`; Compose continues to use port 8000 locally, while Render supplies its public service port (default 10000).

4. **Add the Render Blueprint.**
   - Define one `runtime: docker`, `plan: free` web service using the root Docker context and Render Dockerfile, with `healthCheckPath: /healthz`.
   - Declare non-secret demo/language settings as values. Declare Supabase/Gemini/Sarvam keys and Basic Auth credentials as `sync: false` so Render prompts for them in its dashboard; do not place real values in YAML.
   - Keep the existing Supabase project and schema; set `PARCHA_DEMO_MERCHANT_ID` to the intended seeded merchant in Render.

5. **Verify locally before connecting the public repo.**
   - Build the Render image through Docker and run it locally with test env vars; verify `/`, `/scan`, `/counter`, `/healthz`, `/static`, and `/ws/counter` on one origin.
   - Add focused tests proving missing/wrong Basic credentials get `401` before pipeline/DB/provider work, and auth-disabled local mode still works. Run the backend suite in Docker; do not call Gemini or Sarvam.
   - Verify an authenticated protected request reaches its handler using mocks, and check that generated credential strings never appear in response bodies or logs.

6. **Deploy through Render and hand off the link.**
   - Connect the Git repository/branch to Render and create the Blueprint. Populate secrets only in the Render dashboard; confirm the service plan is Free and wait for `/healthz` to pass.
   - Open the generated HTTPS `onrender.com` URL, check the UI and reconnecting WebSocket, enter the shared demo credentials, then perform one deliberate live scan/resolve only when the user wants to test paid provider calls and DB writes.
   - Give the submission the HTTPS link and the demo credentials through the permitted submission channel. Warm the free service shortly before judging; it may sleep after 15 minutes idle.

## 4. Definition of Done

- A single Render Free Docker web service serves the Angular UI and FastAPI/API/WS/static paths over HTTPS, with `/scan` and `/counter` deep links loading correctly.
- Health check passes; `PORT` binding works in Render and local Compose remains unchanged.
- Missing/wrong credentials are rejected before billable or mutating operations; valid credentials reach the protected route. Browser credentials are not committed or embedded in built assets.
- Existing request/response fields, event names, DB schema, and financial calculations are unchanged. No paid provider request is made during automated verification.
- The user is informed of Render Free sleep/cold-start behavior, ephemeral generated assets, and that live Gemini/Sarvam usage can cost money.
