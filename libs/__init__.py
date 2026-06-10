"""Core library exports and application lifespan."""

import base64
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from pydantic import BaseModel

from configs import get_settings
from libs.ctrl.db import RedisCacheController, init_db
from libs.logger import logger

__all__ = (
    "BaseNotEmptyModel",
    "lifespan",
    "redis_cache",
)

_INSECURE_JWT_SECRET = "change-me-in-production"


def _assert_production_secrets() -> None:
    """生产环境禁止使用默认 JWT 密钥（默认值仅供本地开发，签名可被任何人伪造）。"""
    settings = get_settings()
    if settings.APP_ENV in ("production", "prod") and settings.JWT_SECRET_KEY == _INSECURE_JWT_SECRET:
        raise RuntimeError("生产环境必须显式设置 JWT_SECRET_KEY，禁止使用默认值")


def _ensure_encrypt_key() -> None:
    """ENCRYPT_KEY 未配置时自动生成 Fernet 密钥，写回 settings 并打印到控制台。

    自动生成的密钥仅存活于本进程：重启即更换，用旧密钥加密的数据将无法解密。
    因此把生成值打印出来，便于复制进 .env（ENCRYPT_KEY=...）固化；已显式配置时
    不打印（避免泄漏既有密钥到日志）。生产部署由 compose 强制必填，不会走到这里。
    """
    settings = get_settings()
    if settings.ENCRYPT_KEY:
        return
    # 与 cryptography 的 Fernet.generate_key() 同格式（32 字节 urlsafe base64），
    # 用标准库生成，启动路径不依赖 cryptography 是否安装
    generated = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    settings.ENCRYPT_KEY = generated
    logger.warning(
        "ENCRYPT_KEY 未配置，已自动生成临时密钥（仅本次进程有效，重启即更换）。"
        "请将下行写入 .env 固化：\nENCRYPT_KEY=%s",
        generated,
    )


class BaseNotEmptyModel(BaseModel):
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        for field_info in cls.model_fields.values():
            if field_info.annotation is str and field_info.is_required():
                field_info.metadata.append({"min_length": 1})


redis_cache = RedisCacheController()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    _assert_production_secrets()
    _ensure_encrypt_key()
    await init_db()
    with suppress(Exception):
        await redis_cache.ping()
    yield
    with suppress(Exception):
        await redis_cache.aclose()
