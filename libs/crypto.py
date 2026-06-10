"""业务敏感数据加解密（Fernet 对称加密，密钥为 ENCRYPT_KEY）。

用于交易所 API Key/Secret、bot 实例 api_server 凭证等入库前加密；密文带
``fernet::`` 前缀以区分历史占位密文（``enc::<len>``，不可逆，解密返回 None，
调用方应提示用户重新录入）。

ENCRYPT_KEY 未配置时由 lifespan 自举生成临时密钥（仅本进程有效）；用临时密钥
加密的数据重启后无法解密，生产必须固化 ENCRYPT_KEY（compose 已 ``:?`` 强制）。
"""

from cryptography.fernet import Fernet, InvalidToken

from configs import get_settings

__all__ = (
    "CIPHER_PREFIX",
    "decrypt_text",
    "encrypt_text",
)

CIPHER_PREFIX = "fernet::"


def _fernet() -> Fernet:
    key = get_settings().ENCRYPT_KEY
    if not key:
        raise RuntimeError("ENCRYPT_KEY 未配置，无法加解密敏感数据")
    return Fernet(key.encode("utf-8"))


def encrypt_text(plain: str) -> str:
    """加密明文，返回带前缀的密文。"""
    return CIPHER_PREFIX + _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(cipher: str | None) -> str | None:
    """解密密文；非本格式（历史占位 ``enc::``、空值）或密钥不匹配返回 None。"""
    if not cipher or not cipher.startswith(CIPHER_PREFIX):
        return None
    try:
        return _fernet().decrypt(cipher.removeprefix(CIPHER_PREFIX).encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
