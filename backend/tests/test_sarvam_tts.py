import base64
import io
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services.sarvam_tts import synthesize_alert


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x00" * 32)
    return buffer.getvalue()


class SarvamTtsTests(unittest.TestCase):
    def test_synthesizes_wav_to_static_and_returns_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = SimpleNamespace(
                sarvam_api_key="test-secret",
                tts_language="hi-IN",
                static_dir=Path(temp_dir),
            )
            client = SimpleNamespace(
                text_to_speech=SimpleNamespace(
                    convert=lambda **kwargs: SimpleNamespace(
                        audios=[base64.b64encode(_wav_bytes()).decode("ascii")]
                    )
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
            client_factory.assert_called_once_with(
                api_subscription_key="test-secret", timeout=5.0
            )
            self.assertFalse(list(output.parent.glob("*.tmp")))

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
