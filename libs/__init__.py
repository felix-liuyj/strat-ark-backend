"""Core library exports and application lifespan."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from pydantic import BaseModel

from libs.ctrl.db import RedisCacheController, init_db

__all__ = (
    "BaseNotEmptyModel",
    "lifespan",
    "redis_cache",
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
    await init_db()
    with suppress(Exception):
        await redis_cache.ping()
    yield
    with suppress(Exception):
        await redis_cache.aclose()
