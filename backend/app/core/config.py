"""Runtime configuration for the API gateway (Module 2 slice 1).

Env-driven only — never bake secrets or database URLs into the repo
(AGENTS.md locked decision). See ../.env.example for the documented names.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Upload limits — the frontend (Module 1) already enforces 20 MB client-side;
# this is the server-side mirror of that contract. CIS §4 allows image/pdf.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_CONTENT_TYPES = ("image/jpeg", "image/png", "application/pdf")

# Tally/Marg export formats (CIS §4). Unknown format values are rejected.
EXPORT_FORMATS = ("tally", "marg")

# The only golden sample the CIS §5 fixture defines.
GOLDEN_SAMPLE_ID = "sample_pen_edit_01"


def fixture_candidates() -> tuple:
    """Where the golden fixture may live, in priority order.

    1. PARCHA_FIXTURE_PATH — explicit override (Docker mount or host run).
    2. /contracts/demo_bill_fixture.json — the compose mount of ./contracts
       (backend build context excludes the repo root, so the file is mounted,
       never baked).
    3. <repo-root>/contracts/demo_bill_fixture.json — host runs from backend/
       walking up exactly like the db.py smoke check does.
    """
    candidates = []
    override = os.environ.get("PARCHA_FIXTURE_PATH", "").strip()
    if override:
        candidates.append(Path(override))
    candidates.append(Path("/contracts/demo_bill_fixture.json"))
    candidates.append(Path(__file__).resolve().parents[3] / "contracts" / "demo_bill_fixture.json")
    return tuple(candidates)


@dataclass(frozen=True)
class Settings:
    """Snapshot of the env config at startup time."""

    url: str
    secret_key: str
    demo_merchant_id: str

    @classmethod
    def from_env(cls) -> "Settings":
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
        demo = os.environ.get("PARCHA_DEMO_MERCHANT_ID", "").strip()
        return cls(url=url, secret_key=key, demo_merchant_id=demo)


_settings: Optional["Settings"] = None


def get_settings() -> Settings:
    """Load repo-root .env once and cache the snapshot. Called at app
    startup; routers reuse the cached instance (no per-request re-parse)."""
    global _settings
    if _settings is None:
        load_env()
        _settings = Settings.from_env()
    return _settings


def reset_settings() -> None:
    """Test hook: force the next get_settings() to re-read the env."""
    global _settings
    _settings = None


def load_env() -> None:
    """Load the repo-root .env (same explicit-path rule as db.py: only ever
    the ROOT .env; a subfolder .env would shadow it)."""
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except ImportError:  # python-dotenv is in requirements; tolerate its absence
        pass
