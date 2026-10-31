"""Sarvam translation and Bulbul speech synthesis for Soundbox alerts.

Failure is intentionally non-fatal: callers keep a safe transcript and the
frontend can fall back to browser speech synthesis.
"""

import base64
import logging
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.core.config import get_settings

logger = logging.getLogger("parchapay.api.sarvam_tts")

MODEL = "bulbul:v4-flash"
TRANSLATION_MODEL = "mayura:v1"
TRANSLATION_MODE = "modern-colloquial"
MAX_TRANSLATION_CHARS = 1000
MAX_TEXT_CHARS = 2500
REQUEST_TIMEOUT_SECONDS = 5.0
_PROTECTED_VALUE = re.compile(
    r"\bINV-[A-Z0-9-]+\b|(?<![A-Z0-9])\d[\d,]*(?:\.\d+)?(?![A-Z0-9])",
    re.IGNORECASE,
)


def translate_alert(transcript: str) -> Optional[str]:
    """Translate the deterministic alert into the configured spoken language.

    Numeric values and invoice identifiers are replaced with checked tokens
    during translation, then restored byte-for-byte. Translation failure is
    non-fatal and returns None so callers do not send source-language text to
    a mismatched TTS language.
    """
    settings = get_settings()
    text = (transcript or "").strip()
    if not text or len(text) > MAX_TRANSLATION_CHARS:
        logger.warning("Sarvam translation skipped reason=invalid_text length=%d", len(text))
        return None
    if settings.translation_source_language.casefold() == settings.translation_target_language.casefold():
        return text
    if not settings.sarvam_api_key:
        logger.info("Sarvam translation skipped reason=missing_api_key")
        return None

    protected_values: list[tuple[str, str]] = []

    def protect(match: re.Match[str]) -> str:
        token = f"ZQXNUM{len(protected_values):03d}QXZ"
        protected_values.append((token, match.group(0)))
        return token

    protected_text = _PROTECTED_VALUE.sub(protect, text)
    try:
        from sarvamai import SarvamAI

        client = SarvamAI(
            api_subscription_key=settings.sarvam_api_key,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response = client.text.translate(
            input=protected_text,
            source_language_code=settings.translation_source_language,
            target_language_code=settings.translation_target_language,
            model=TRANSLATION_MODEL,
            mode=TRANSLATION_MODE,
            output_script="fully-native",
        )
        translated = (getattr(response, "translated_text", None) or "").strip()
        if not translated:
            logger.warning("Sarvam translation returned empty text")
            return None

        for token, original_value in protected_values:
            if translated.count(token) != 1:
                logger.warning("Sarvam translation rejected reason=numeric_token_mismatch")
                return None
            translated = translated.replace(token, original_value)
        return translated
    except Exception as exc:
        # SDK exceptions may contain provider response details; log type only.
        logger.warning("Sarvam translation failed error_type=%s", type(exc).__name__)
        return None


def synthesize_alert(transcript: str, invoice_id: str) -> Optional[str]:
    """Synthesize an alert WAV and return its `/static` URL, else `None`.

    This function is synchronous by design and must be called from a worker
    thread by async request handlers. API credentials and response bodies are
    never logged.
    """
    settings = get_settings()
    text = (transcript or "").strip()
    if not settings.sarvam_api_key:
        logger.info("Sarvam TTS skipped reason=missing_api_key")
        return None
    if not text or len(text) > MAX_TEXT_CHARS:
        logger.warning("Sarvam TTS skipped reason=invalid_text length=%d", len(text))
        return None

    temp_path: Optional[Path] = None
    try:
        from sarvamai import SarvamAI

        client = SarvamAI(
            api_subscription_key=settings.sarvam_api_key,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response = client.text_to_speech.convert(
            text=text,
            model=MODEL,
            language_code=settings.tts_language,
            speaker=settings.tts_speaker,
            output_audio_codec="wav",
            speech_sample_rate=24000,
        )
        audios = getattr(response, "audios", None) or []
        if not audios:
            logger.warning("Sarvam TTS returned no audio")
            return None

        audio_bytes = base64.b64decode("".join(audios), validate=True)
        if len(audio_bytes) < 12 or audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
            logger.warning("Sarvam TTS returned invalid WAV data")
            return None

        audio_dir = settings.static_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        safe_invoice_id = re.sub(r"[^A-Za-z0-9_-]", "_", invoice_id)[:80] or uuid4().hex
        filename = f"alert_{safe_invoice_id}.wav"
        output_path = audio_dir / filename
        temp_path = audio_dir / f".{filename}.{uuid4().hex}.tmp"
        temp_path.write_bytes(audio_bytes)
        temp_path.replace(output_path)
        logger.info("Sarvam TTS audio generated invoice_id=%s bytes=%d", safe_invoice_id, len(audio_bytes))
        return f"/static/audio/{filename}"
    except Exception as exc:
        # SDK errors may contain provider response details; log type only.
        logger.warning("Sarvam TTS failed error_type=%s", type(exc).__name__)
        return None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("could not remove temporary Sarvam WAV")
