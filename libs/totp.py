"""TOTP 两步验证工具（pyotp 封装）。

secret 由 ``generate_secret`` 生成、经 libs/crypto Fernet 加密存于 system_configs；
绑定时返回 otpauth URI 供 Authenticator 扫码，确认开启 / 关闭均需校验当前验证码。
"""

import pyotp

__all__ = (
    "generate_secret",
    "provisioning_uri",
    "verify_code",
)

_ISSUER = "StratArk"


def generate_secret() -> str:
    """生成 base32 TOTP secret。"""
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    """otpauth:// URI（Authenticator 扫码绑定用），account 取用户邮箱。"""
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=_ISSUER)


def verify_code(secret: str, code: str) -> bool:
    """校验 6 位验证码；容忍前后各一个时间窗（±30s）的时钟偏差。"""
    cleaned = (code or "").strip().replace(" ", "")
    if not cleaned or not secret:
        return False
    return pyotp.TOTP(secret).verify(cleaned, valid_window=1)
