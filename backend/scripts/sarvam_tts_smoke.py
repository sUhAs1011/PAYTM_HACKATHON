"""Make one Sarvam Bulbul TTS call using the repository's ignored root .env."""

import base64
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sarvamai import SarvamAI


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root / ".env")
    api_key = os.environ.get("SARVAM_API_KEY", "").strip()
    language = os.environ.get("PARCHA_TTS_LANGUAGE", "hi-IN").strip() or "hi-IN"
    if not api_key:
        print("SARVAM_API_KEY is not set in the repository-root .env; no API call made.", file=sys.stderr)
        return 2

    fixture_path = repo_root / "contracts" / "demo_bill_fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    text = fixture["voice_transcript"]
    client = SarvamAI(api_subscription_key=api_key, timeout=20.0)
    try:
        response = client.text_to_speech.convert(
            text=text,
            model="bulbul:v4-flash",
            language_code=language,
            output_audio_codec="wav",
            speech_sample_rate=24000,
        )
    except Exception as exc:
        # Provider SDK exception bodies are omitted to avoid accidental secret disclosure.
        print(f"Sarvam TTS request failed ({type(exc).__name__}).", file=sys.stderr)
        return 1

    audios = getattr(response, "audios", None) or []
    if not audios:
        print("Sarvam returned no audio.", file=sys.stderr)
        return 1
    audio_bytes = base64.b64decode("".join(audios), validate=True)
    if len(audio_bytes) < 12 or audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        print("Sarvam response was not a valid WAV file.", file=sys.stderr)
        return 1

    output_path = repo_root / "backend" / "static" / "audio" / "sarvam_smoke.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio_bytes)
    print(f"Sarvam TTS succeeded ({language}, bulbul:v4-flash).")
    print(f"WAV: {output_path.relative_to(repo_root)} ({len(audio_bytes)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
