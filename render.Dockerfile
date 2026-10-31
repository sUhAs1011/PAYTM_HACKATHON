# Build the Angular app from the repo root so its shared @contracts paths resolve.
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /workspace
COPY contracts/ ./contracts/
COPY frontend/ ./frontend/
WORKDIR /workspace/frontend
RUN npm install --no-audit --no-fund \
    && npx ng build --configuration production

FROM python:3.12-slim-bookworm AS python-builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime
RUN groupadd --gid 1001 app \
    && useradd --uid 1001 --gid 1001 --create-home --no-log-init app
WORKDIR /app
COPY --from=python-builder /opt/venv /opt/venv
COPY --chown=app:app backend/ ./
COPY --chown=app:app contracts/ ./contracts/
COPY --chown=app:app contracts/ /contracts/
COPY --from=frontend-build --chown=app:app /workspace/frontend/dist/parchapay-frontend/browser ./frontend-dist/
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PARCHA_FIXTURE_PATH=/contracts/demo_bill_fixture.json
USER app
EXPOSE 10000
CMD ["/bin/sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
