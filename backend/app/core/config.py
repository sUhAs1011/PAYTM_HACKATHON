"""Application configuration & environment variables."""

import os
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel


class Settings(BaseModel):
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip().strip('"\'')
    environment: str = os.getenv("ENVIRONMENT", "development")

    # Path resolution: works inside Docker (/app/static) and locally (backend/static)
    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    static_dir: Path = (
        Path("/app/static")
        if Path("/app/static").exists()
        else (Path(__file__).resolve().parent.parent / "static")
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
