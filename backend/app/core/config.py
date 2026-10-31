"""Runtime settings shared by the API, Gemini, and Sarvam voice pipeline.

Settings are loaded from the repo-root `.env` for host runs and from Compose's
backend environment for container runs. Secrets are never checked into this
repository.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Upload limits mirror the Angular scanner and CIS image/PDF contract.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_CONTENT_TYPES = ("image/jpeg", "image/png", "application/pdf")
EXPORT_FORMATS = ("tally", "marg")
GOLDEN_SAMPLE_ID = "sample_pen_edit_01"


def fixture_candidates() -> tuple[Path, ...]:
    """Return candidate paths to the golden fixture, explicit override first."""
    candidates: list[Path] = []
    override = os.environ.get("PARCHA_FIXTURE_PATH", "").strip()
    if override:
        candidates.append(Path(override))
    candidates.append(Path("/contracts/demo_bill_fixture.json"))
    candidates.append(Path(__file__).resolve().parents[3] / "contracts" / "demo_bill_fixture.json")
    return tuple(candidates)


@dataclass(frozen=True)
class Settings:
    url: str
    secret_key: str
    demo_merchant_id: str
    demo_auth_enabled: bool
    demo_auth_username: str
    demo_auth_password: str
    gemini_api_key: str
    sarvam_api_key: str
    translation_source_language: str
    translation_target_language: str
    tts_language: str
    tts_speaker: str
    environment: str
    base_dir: Path
    static_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        backend_dir = Path(__file__).resolve().parents[2]
        api_key = os.environ.get("GEMINI_API_KEY", "").strip().strip("\"'")
        demo_auth_enabled = _env_bool("PARCHA_DEMO_AUTH_ENABLED", default=False)
        demo_auth_username = os.environ.get("PARCHA_DEMO_AUTH_USERNAME", "").strip()
        demo_auth_password = os.environ.get("PARCHA_DEMO_AUTH_PASSWORD", "").strip()
        if demo_auth_enabled and not (demo_auth_username and demo_auth_password):
            raise ValueError(
                "PARCHA_DEMO_AUTH_USERNAME and PARCHA_DEMO_AUTH_PASSWORD are required "
                "when PARCHA_DEMO_AUTH_ENABLED is true"
            )
        tts_language = os.environ.get("PARCHA_TTS_LANGUAGE", "hi-IN").strip() or "hi-IN"
        translation_target_language = (
            os.environ.get("PARCHA_TRANSLATION_TARGET_LANGUAGE", tts_language).strip() or tts_language
        )
        if translation_target_language.casefold() != tts_language.casefold():
            raise ValueError("PARCHA_TRANSLATION_TARGET_LANGUAGE must match PARCHA_TTS_LANGUAGE")
        return cls(
            url=os.environ.get("SUPABASE_URL", "").strip(),
            secret_key=os.environ.get("SUPABASE_SECRET_KEY", "").strip(),
            demo_merchant_id=os.environ.get("PARCHA_DEMO_MERCHANT_ID", "").strip(),
            demo_auth_enabled=demo_auth_enabled,
            demo_auth_username=demo_auth_username,
            demo_auth_password=demo_auth_password,
            gemini_api_key=api_key,
            sarvam_api_key=os.environ.get("SARVAM_API_KEY", "").strip().strip("\"'"),
            translation_source_language=(
                os.environ.get("PARCHA_TRANSLATION_SOURCE_LANGUAGE", "en-IN").strip() or "en-IN"
            ),
            translation_target_language=translation_target_language,
            tts_language=tts_language,
            tts_speaker=os.environ.get("PARCHA_TTS_SPEAKER", "aparna_hi_customer").strip()
            or "aparna_hi_customer",
            environment=os.environ.get("ENVIRONMENT", "development").strip(),
            base_dir=backend_dir,
            static_dir=backend_dir / "static",
        )


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Load and cache runtime settings (root `.env` on host, env in Compose)."""
    global _settings
    if _settings is None:
        load_env()
        _settings = Settings.from_env()
    return _settings


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def reset_settings() -> None:
    """Test hook for environment changes between in-process test cases."""
    global _settings
    _settings = None


def load_env() -> None:
    """Load only the repository-root .env; a subfolder file must not shadow it."""
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except ImportError:  # python-dotenv is a declared backend dependency
        return
