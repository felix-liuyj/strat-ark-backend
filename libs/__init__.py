"""Core library exports and application lifespan."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

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


def _assert_production_secrets() -> None:
    """生产环境禁止使用默认 JWT 密钥（默认值仅供本地开发，签名可被任何人伪造）。"""
    settings = get_settings()
    if settings.APP_ENV in ("production", "prod") and settings.JWT_SECRET_KEY == _INSECURE_JWT_SECRET:
        raise RuntimeError("生产环境必须显式设置 JWT_SECRET_KEY，禁止使用默认值")


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
    yield
    with suppress(Exception):
        await redis_cache.aclose()
