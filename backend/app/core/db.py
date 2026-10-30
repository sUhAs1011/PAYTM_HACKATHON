"""Async Supabase client for ParchaPay AI (Module 2/5, Dev 2 territory).

The client talks to PostgREST over HTTPS using the project URL and the
service_role secret key, which bypasses row level security on the CIS
tables. No database name or password is needed for this transport; those
are only for direct Postgres connections, which this client never opens.

Environment variables (see .env.example):
    SUPABASE_URL          Project URL, e.g. https://<project-ref>.supabase.co
    SUPABASE_SECRET_KEY   service_role secret key (JWT with role=service_role,
                          or a new-format sb_secret_ key)
"""

import asyncio
import os
from typing import Optional

from supabase import AsyncClient, create_async_client

_client: Optional[AsyncClient] = None
_init_lock = asyncio.Lock()


async def get_client() -> AsyncClient:
    """Return the shared async Supabase client, creating it on first use."""
    global _client
    if _client is None:
        async with _init_lock:
            if _client is None:
                _client = await _create_client()
    return _client


def reset_client() -> None:
    """Drop the cached client so the next get_client() creates a fresh one.

    The client binds to the event loop it was created on. In the deployed
    app there is exactly one loop, so this is never needed — it exists for
    test contexts that mix `asyncio.run()` with Starlette's TestClient
    (whose portal runs its own loop)."""
    global _client
    _client = None


async def _create_client() -> AsyncClient:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", url),
            ("SUPABASE_SECRET_KEY", key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing environment variable(s): "
            + ", ".join(missing)
            + ". Set them in .env (see .env.example)."
        )
    return await create_async_client(url, key)


if __name__ == "__main__":
    # Smoke check: list every CIS table with its exact row count.
    # Run from backend/ with:  python -m app.core.db
    import base64
    import json
    from pathlib import Path

    from dotenv import load_dotenv

    CIS_TABLES = (
        "merchants",
        "suppliers",
        "canonical_skus",
        "invoices",
        "invoice_line_items",
        "gst_ims_records",
        "split_credit_loans",
    )

    # User-approved auxiliary tables outside the 7-table CIS (see AGENTS.md).
    AUX_TABLES = (
        "transactions",
        "merchant_account_ledger",
    )

    # Load the repo-root .env explicitly (backend/app/core/db.py -> parents[3]
    # is the repository root), so the check works from any cwd and cannot be
    # shadowed by a stray .env in a subfolder.
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")

    def _describe_key(key: str) -> str:
        """Identify the key type without any network call, so a mistakenly
        used publishable/anon key is caught before it silently reads zero
        rows through RLS."""
        if key.startswith("sb_secret_"):
            return "secret key (new format)"
        if key.startswith("sbp_") or key.startswith("sb_publishable_"):
            return "publishable key - RLS will hide every table"
        try:
            payload = key.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            role = json.loads(base64.urlsafe_b64decode(payload)).get("role")
        except (IndexError, ValueError):
            return "unrecognized format"
        if role == "service_role":
            return "service_role JWT"
        return "JWT role={} - RLS will hide every table".format(role)

    async def _check() -> int:
        client = await get_client()
        print("Supabase URL: {}".format(os.environ.get("SUPABASE_URL", "")))
        print("Key type:     {}".format(_describe_key(os.environ.get("SUPABASE_SECRET_KEY", ""))))
        print("Row counts (zeros are expected until the demo seed is applied):")
        failed = False
        for section_name, tables in (
            ("CIS tables (Engineering Document contract):", CIS_TABLES),
            ("Auxiliary tables (user-approved deviations):", AUX_TABLES),
        ):
            print(section_name)
            for table in tables:
                try:
                    response = await client.table(table).select("*", count="exact").execute()
                    print("  {}: {} rows".format(table, response.count))
                except Exception as exc:  # report every table, then exit non-zero
                    failed = True
                    print("  {}: ERROR {}".format(table, exc))
        if failed:
            print("FAILED: one or more tables could not be read.")
        else:
            print("OK: all 7 CIS tables and {} auxiliary tables reachable.".format(len(AUX_TABLES)))
        return 1 if failed else 0

    raise SystemExit(asyncio.run(_check()))
