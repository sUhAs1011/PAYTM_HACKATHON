"""Sarvam translation and Bulbul speech synthesis for Soundbox alerts.

Failure is intentionally non-fatal: callers keep a safe transcript and the
frontend can fall back to browser speech synthesis.
"""

import base64
import logging
import re
from collections import Counter, defaultdict, deque
from decimal import Decimal, InvalidOperation
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
_INVOICE_ID = re.compile(r"\bINV-[A-Z0-9-]+\b", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![A-Z0-9])\d[\d,]*(?:\.\d+)?(?![A-Z0-9])")
_FINANCIAL_VALUE = re.compile(
    rf"{_INVOICE_ID.pattern}|{_NUMBER.pattern}",
    re.IGNORECASE,
)


def translate_alert(transcript: str) -> Optional[str]:
    """Translate the deterministic alert into the configured spoken language.

    Translate natural text with Sarvam's international numeral format, then
    validate and restore the original spelling of every invoice ID and
    numeric value. Provider output is never trusted to change financial data.
    Translation failure returns None so callers retain the source transcript.
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

    try:
        from sarvamai import SarvamAI

        client = SarvamAI(
            api_subscription_key=settings.sarvam_api_key,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response = client.text.translate(
            input=text,
            source_language_code=settings.translation_source_language,
            target_language_code=settings.translation_target_language,
            model=TRANSLATION_MODEL,
            mode=TRANSLATION_MODE,
            output_script="fully-native",
            numerals_format="international",
        )
        translated = (getattr(response, "translated_text", None) or "").strip()
        if not translated:
            logger.warning("Sarvam translation returned empty text")
            return None
        return _validate_and_restore_financial_values(text, translated)
    except Exception as exc:
        # SDK exceptions may contain provider response details; log type only.
        logger.warning("Sarvam translation failed error_type=%s", type(exc).__name__)
        return None


def _financial_value_key(value: str) -> tuple[str, object]:
    """Return a comparison key for an invoice ID or localized numeric token."""
    if _INVOICE_ID.fullmatch(value):
        return "invoice_id", value.casefold()
    try:
        return "number", Decimal(value.replace(",", ""))
    except InvalidOperation:
        # _NUMBER only matches decimal digits and separators; this is a
        # defensive fallback that still makes an unexpected value fail closed.
        return "invalid_number", value


def _validate_and_restore_financial_values(source: str, translated: str) -> Optional[str]:
    """Reject changed/added values, and restore equivalent values verbatim.

    Mayura may adjust punctuation/grouping. Comparing parsed numeric values
    lets us accept harmless formatting changes while restoring the exact
    source spelling. Invoice IDs must retain the same complete identifier.
    Only counts/validation outcomes are logged; transcript contents are not.
    """
    source_tokens = [match.group(0) for match in _FINANCIAL_VALUE.finditer(source)]
    translated_tokens = [
        match.group(0) for match in _FINANCIAL_VALUE.finditer(translated)
    ]
    source_counts = Counter(_financial_value_key(token) for token in source_tokens)
    translated_counts = Counter(
        _financial_value_key(token) for token in translated_tokens
    )
    if source_counts != translated_counts:
        logger.warning("Sarvam translation rejected reason=financial_value_mismatch")
        return None

    originals: dict[tuple[str, object], deque[str]] = defaultdict(deque)
    for token in source_tokens:
        originals[_financial_value_key(token)].append(token)

    def restore(match: re.Match[str]) -> str:
        key = _financial_value_key(match.group(0))
        return originals[key].popleft()

    return _FINANCIAL_VALUE.sub(restore, translated)


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
