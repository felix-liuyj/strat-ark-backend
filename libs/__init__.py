"""Core library exports and application lifespan."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from cryptography.fernet import Fernet
from fastapi import FastAPI
from pydantic import BaseModel

from configs import get_settings
from libs.ctrl.db import RedisCacheController, init_db

__all__ = (
    "BaseNotEmptyModel",
    "lifespan",
    "redis_cache",
)

_INSECURE_JWT_SECRET = "change-me-in-production"
_MIN_PRODUCTION_JWT_SECRET_LENGTH = 32


def _assert_production_secrets() -> None:
    """校验已配置的加密密钥，并在生产环境强制校验全部核心密钥。"""
    settings = get_settings()
    production = settings.APP_ENV.strip().lower() in ("production", "prod")
    encrypt_key = (settings.ENCRYPT_KEY or "").strip()
    if encrypt_key:
        try:
            Fernet(encrypt_key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("ENCRYPT_KEY 必须是有效的 Fernet 密钥") from exc
    if not production:
        return
    jwt_secret = settings.JWT_SECRET_KEY.strip()
    if jwt_secret == _INSECURE_JWT_SECRET or len(jwt_secret) < _MIN_PRODUCTION_JWT_SECRET_LENGTH:
        raise RuntimeError("生产环境 JWT_SECRET_KEY 必须显式设置且不少于 32 个字符")
    if not encrypt_key:
        raise RuntimeError("生产环境 ENCRYPT_KEY 必须显式设置为有效的 Fernet 密钥")


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
    await init_db()
    with suppress(Exception):
        await redis_cache.ping()
    # Bot 实例守护：状态对账 + 日亏熔断（编排器未配置时每轮静默跳过）。
    from libs.guardian import start_guardian, stop_guardian

    start_guardian()
    yield
    await stop_guardian()
    with suppress(Exception):
        await redis_cache.aclose()
