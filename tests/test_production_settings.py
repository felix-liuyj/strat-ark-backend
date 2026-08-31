"""生产启动配置门禁。"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet

from libs import _assert_production_secrets


class ProductionSettingsTest(unittest.TestCase):
    def test_rejects_short_jwt_secret(self) -> None:
        settings = SimpleNamespace(
            APP_ENV="production",
            JWT_SECRET_KEY="too-short",
            ENCRYPT_KEY=Fernet.generate_key().decode(),
        )

        with patch("libs.get_settings", return_value=settings), self.assertRaisesRegex(RuntimeError, "JWT_SECRET_KEY"):
            _assert_production_secrets()

    def test_rejects_invalid_encrypt_key(self) -> None:
        settings = SimpleNamespace(APP_ENV="production", JWT_SECRET_KEY="a" * 32, ENCRYPT_KEY="invalid")

        with patch("libs.get_settings", return_value=settings), self.assertRaisesRegex(RuntimeError, "ENCRYPT_KEY"):
            _assert_production_secrets()

    def test_accepts_valid_production_secrets(self) -> None:
        settings = SimpleNamespace(
            APP_ENV="production",
            JWT_SECRET_KEY="a" * 32,
            ENCRYPT_KEY=Fernet.generate_key().decode(),
        )

        with patch("libs.get_settings", return_value=settings):
            _assert_production_secrets()


if __name__ == "__main__":
    unittest.main()
