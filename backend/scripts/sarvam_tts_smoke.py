"""Make a Sarvam Translate → Bulbul smoke call using the ignored root .env."""

import json
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.core.config import get_settings
from app.services.sarvam_tts import synthesize_alert, translate_alert


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root / ".env")
    settings = get_settings()
    if not settings.sarvam_api_key:
        print("SARVAM_API_KEY is not set in the repository-root .env; no API call made.", file=sys.stderr)
        return 2

    fixture_path = repo_root / "contracts" / "demo_bill_fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    translated = translate_alert(fixture["voice_transcript"])
    if translated is None:
        print("Sarvam translation failed; no TTS request made.", file=sys.stderr)
        return 1
    audio_url = synthesize_alert(translated, fixture["invoice_id"])
    if not audio_url:
        print("Sarvam TTS failed or returned no audio.", file=sys.stderr)
        return 1

    generated_path = settings.static_dir / audio_url.removeprefix("/static/")
    if not generated_path.is_file():
        print("Sarvam TTS returned a URL without a local WAV file.", file=sys.stderr)
        return 1

    output_path = repo_root / "backend" / "static" / "audio" / "sarvam_smoke.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(generated_path, output_path)
    print(
        "Sarvam Translate → TTS succeeded "
        f"({settings.translation_source_language} → {settings.tts_language}, "
        f"{settings.tts_speaker}, bulbul:v4-flash)."
    )
    print(f"WAV: {output_path.relative_to(repo_root)} ({output_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
