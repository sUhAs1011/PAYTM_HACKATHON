import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app.core.config import Settings
from app.core.demo_auth import require_demo_auth


class DemoAuthTests(unittest.TestCase):
    def test_auth_is_off_by_default_for_local_development(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertFalse(settings.demo_auth_enabled)
        self.assertEqual(settings.demo_auth_username, "")
        self.assertEqual(settings.demo_auth_password, "")

    def test_enabled_auth_requires_both_credentials(self):
        with patch.dict(
            os.environ,
            {"PARCHA_DEMO_AUTH_ENABLED": "true", "PARCHA_DEMO_AUTH_USERNAME": "demo"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "are required"):
                Settings.from_env()

    def test_basic_auth_accepts_only_configured_credentials(self):
        settings = SimpleNamespace(
            demo_auth_enabled=True,
            demo_auth_username="demo-user",
            demo_auth_password="test-password",
        )
        with patch("app.core.demo_auth.get_settings", return_value=settings):
            require_demo_auth(
                HTTPBasicCredentials(username="demo-user", password="test-password")
            )
            with self.assertRaises(HTTPException) as caught:
                require_demo_auth(
                    HTTPBasicCredentials(username="demo-user", password="wrong")
                )

        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.headers["WWW-Authenticate"], 'Basic realm="ParchaPay Demo"')

    def test_disabled_auth_allows_local_requests(self):
        settings = SimpleNamespace(demo_auth_enabled=False)
        with patch("app.core.demo_auth.get_settings", return_value=settings):
            require_demo_auth(None)


if __name__ == "__main__":
    unittest.main()
