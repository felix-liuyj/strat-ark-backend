"""JSON 配置中的敏感字段加密、解密与响应掩码。"""

from typing import Any

from libs.crypto import CIPHER_PREFIX, decrypt_text, encrypt_text

__all__ = (
    "ENGINE_SENSITIVE_CONFIG_KEYS",
    "MASKED_CONFIG_VALUE",
    "NOTIFICATION_SENSITIVE_CONFIG_KEYS",
    "decrypt_sensitive_config",
    "mask_sensitive_config",
    "merge_sensitive_config",
)

MASKED_CONFIG_VALUE = "***"
ENGINE_SENSITIVE_CONFIG_KEYS = frozenset(
    {"token", "apiKey", "secret", "restApiToken", "password", "orchestratorToken"}
)
NOTIFICATION_SENSITIVE_CONFIG_KEYS = frozenset(
    {"botToken", "secret", "apiKey", "token", "password", "url", "webhookUrl", "deviceToken"}
)


def mask_sensitive_config(config: dict[str, Any], sensitive_keys: frozenset[str]) -> dict[str, Any]:
    return {
        key: MASKED_CONFIG_VALUE if key in sensitive_keys and value else value
        for key, value in config.items()
    }


def decrypt_sensitive_config(config: dict[str, Any], sensitive_keys: frozenset[str]) -> dict[str, Any]:
    decrypted = dict(config)
    for key in sensitive_keys:
        value = decrypted.get(key)
        if isinstance(value, str) and value.startswith(CIPHER_PREFIX):
            decrypted[key] = decrypt_text(value) or ""
    return decrypted


def merge_sensitive_config(
    stored: dict[str, Any], incoming: dict[str, Any], sensitive_keys: frozenset[str]
) -> dict[str, Any]:
    """合并显式写入，并在该写路径顺带迁移历史明文敏感字段。"""
    merged = _encrypt_legacy_values(stored, sensitive_keys)
    for key, value in incoming.items():
        if key not in sensitive_keys:
            merged[key] = value
            continue
        if value == MASKED_CONFIG_VALUE:
            continue
        text = str(value or "").strip()
        merged[key] = encrypt_text(text) if text else ""
    return merged


def _encrypt_legacy_values(config: dict[str, Any], sensitive_keys: frozenset[str]) -> dict[str, Any]:
    migrated = dict(config)
    for key in sensitive_keys:
        value = migrated.get(key)
        if not isinstance(value, str) or not value or value.startswith(CIPHER_PREFIX):
            continue
        migrated[key] = encrypt_text(value)
    return migrated
