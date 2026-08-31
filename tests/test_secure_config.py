"""敏感 JSON 配置不得明文落库或由响应回显。"""

import unittest
from unittest.mock import patch

from libs.secure_config import (
    MASKED_CONFIG_VALUE,
    decrypt_sensitive_config,
    mask_sensitive_config,
    merge_sensitive_config,
)

_KEYS = frozenset({"token"})


class SecureConfigTest(unittest.TestCase):
    def test_new_secret_is_encrypted_and_masked(self) -> None:
        with patch("libs.secure_config.encrypt_text", return_value="fernet::cipher"):
            stored = merge_sensitive_config({}, {"token": "plain", "url": "https://example.test"}, _KEYS)

        self.assertEqual("fernet::cipher", stored["token"])
        self.assertEqual(MASKED_CONFIG_VALUE, mask_sensitive_config(stored, _KEYS)["token"])

    def test_mask_placeholder_preserves_existing_secret(self) -> None:
        stored = merge_sensitive_config(
            {"token": "fernet::cipher"},
            {"token": MASKED_CONFIG_VALUE},
            _KEYS,
        )

        self.assertEqual("fernet::cipher", stored["token"])

    def test_encrypted_secret_is_decrypted_for_runtime_only(self) -> None:
        with patch("libs.secure_config.decrypt_text", return_value="plain"):
            config = decrypt_sensitive_config({"token": "fernet::cipher"}, _KEYS)

        self.assertEqual("plain", config["token"])


if __name__ == "__main__":
    unittest.main()
