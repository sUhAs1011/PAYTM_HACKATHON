import base64
import io
import os
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.config import Settings
from app.services.sarvam_tts import synthesize_alert, translate_alert


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x00" * 32)
    return buffer.getvalue()


class SarvamTtsTests(unittest.TestCase):
    def test_voice_languages_are_configurable_and_must_match(self):
        with patch.dict(
            os.environ,
            {
                "PARCHA_TRANSLATION_SOURCE_LANGUAGE": "en-IN",
                "PARCHA_TRANSLATION_TARGET_LANGUAGE": "hi-IN",
                "PARCHA_TTS_LANGUAGE": "hi-IN",
                "PARCHA_TTS_SPEAKER": "aparna_hi_customer",
            },
            clear=True,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.translation_source_language, "en-IN")
        self.assertEqual(settings.translation_target_language, "hi-IN")
        self.assertEqual(settings.tts_language, "hi-IN")
        self.assertEqual(settings.tts_speaker, "aparna_hi_customer")

        with patch.dict(
            os.environ,
            {
                "PARCHA_TRANSLATION_TARGET_LANGUAGE": "hi-IN",
                "PARCHA_TTS_LANGUAGE": "kn-IN",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "must match"):
                Settings.from_env()

    def test_synthesizes_wav_to_static_and_returns_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = SimpleNamespace(
                sarvam_api_key="test-secret",
                translation_source_language="en-IN",
                translation_target_language="hi-IN",
                tts_language="hi-IN",
                tts_speaker="aparna_hi_customer",
                static_dir=Path(temp_dir),
            )
            convert = Mock(
                return_value=SimpleNamespace(
                    audios=[base64.b64encode(_wav_bytes()).decode("ascii")]
                )
            )
            client = SimpleNamespace(
                text_to_speech=SimpleNamespace(
                    convert=convert
                )
            )
            with (
                patch("app.services.sarvam_tts.get_settings", return_value=settings),
                patch("sarvamai.SarvamAI", return_value=client) as client_factory,
            ):
                url = synthesize_alert("Invoice checked.", "invoice-123")

            self.assertEqual(url, "/static/audio/alert_invoice-123.wav")
            output = Path(temp_dir) / "audio" / "alert_invoice-123.wav"
            self.assertEqual(output.read_bytes(), _wav_bytes())
            convert.assert_called_once_with(
                text="Invoice checked.",
                model="bulbul:v4-flash",
                language_code="hi-IN",
                speaker="aparna_hi_customer",
                output_audio_codec="wav",
                speech_sample_rate=24000,
            )
            client_factory.assert_called_once_with(
                api_subscription_key="test-secret", timeout=5.0
            )
            self.assertFalse(list(output.parent.glob("*.tmp")))

    def test_translates_alert_and_restores_financial_values_exactly(self):
        settings = SimpleNamespace(
            sarvam_api_key="test-secret",
            translation_source_language="en-IN",
            translation_target_language="hi-IN",
        )
        translation_call = Mock(
            return_value=SimpleNamespace(
                translated_text=(
                    "इनवॉइस ZQXNUM000QXZ में अतिरिक्त राशि ZQXNUM001QXZ है। "
                    "भुगतान ZQXNUM002QXZ करें।"
                )
            )
        )
        client = SimpleNamespace(text=SimpleNamespace(translate=translation_call))
        original = "Invoice INV-2026-402 has an overcharge of Rs 140; pay Rs 13,860."

        with (
            patch("app.services.sarvam_tts.get_settings", return_value=settings),
            patch("sarvamai.SarvamAI", return_value=client) as client_factory,
        ):
            translated = translate_alert(original)

        self.assertEqual(
            translated,
            "इनवॉइस INV-2026-402 में अतिरिक्त राशि 140 है। भुगतान 13,860 करें।",
        )
        kwargs = translation_call.call_args.kwargs
        self.assertEqual(kwargs["source_language_code"], "en-IN")
        self.assertEqual(kwargs["target_language_code"], "hi-IN")
        self.assertEqual(kwargs["model"], "mayura:v1")
        self.assertEqual(kwargs["mode"], "modern-colloquial")
        self.assertEqual(kwargs["output_script"], "fully-native")
        client_factory.assert_called_once_with(
            api_subscription_key="test-secret", timeout=5.0
        )

    def test_translation_returns_none_when_key_or_number_placeholders_are_missing(self):
        settings = SimpleNamespace(
            sarvam_api_key="",
            translation_source_language="en-IN",
            translation_target_language="hi-IN",
        )
        with (
            patch("app.services.sarvam_tts.get_settings", return_value=settings),
            patch("sarvamai.SarvamAI") as client_factory,
        ):
            self.assertIsNone(translate_alert("Pay Rs 100."))
            client_factory.assert_not_called()

        settings.sarvam_api_key = "test-secret"
        client = SimpleNamespace(
            text=SimpleNamespace(
                translate=Mock(return_value=SimpleNamespace(translated_text="भुगतान करें।"))
            )
        )
        with (
            patch("app.services.sarvam_tts.get_settings", return_value=settings),
            patch("sarvamai.SarvamAI", return_value=client),
        ):
            self.assertIsNone(translate_alert("Pay Rs 100."))

    def test_missing_key_or_provider_error_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = SimpleNamespace(
                sarvam_api_key="",
                tts_language="hi-IN",
                static_dir=Path(temp_dir),
            )
            with (
                patch("app.services.sarvam_tts.get_settings", return_value=settings),
                patch("sarvamai.SarvamAI") as client_factory,
            ):
                self.assertIsNone(synthesize_alert("Invoice checked.", "invoice-123"))
                client_factory.assert_not_called()

            settings.sarvam_api_key = "test-secret"
            with (
                patch("app.services.sarvam_tts.get_settings", return_value=settings),
                patch("sarvamai.SarvamAI", side_effect=TimeoutError()),
            ):
                self.assertIsNone(synthesize_alert("Invoice checked.", "invoice-123"))

    def test_rejects_empty_or_overlong_text_without_api_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = SimpleNamespace(
                sarvam_api_key="test-secret",
                tts_language="hi-IN",
                static_dir=Path(temp_dir),
            )
            with (
                patch("app.services.sarvam_tts.get_settings", return_value=settings),
                patch("sarvamai.SarvamAI") as client_factory,
            ):
                self.assertIsNone(synthesize_alert("  ", "invoice-123"))
                self.assertIsNone(synthesize_alert("x" * 2501, "invoice-123"))
                client_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
