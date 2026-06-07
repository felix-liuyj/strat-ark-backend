"""Health check view models."""

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from configs import get_settings
from libs import redis_cache
from responses.common.health import StatusResponseData
from view_models.common.base import BaseViewModel

__all__ = ("QueryHealthStatusViewModel",)


class QueryHealthStatusViewModel(BaseViewModel):
    def __init__(self, request: Request, db: AsyncSession) -> None:
        super().__init__(request=request)
        self.db = db

    async def before(self) -> None:
        await super().before()
        database_ok = False
        redis_ok: bool | None = None

        try:
            await self.db.execute(text("SELECT 1"))
            database_ok = True
        except Exception:
            database_ok = False

        if redis_cache is not None:
            try:
                await redis_cache.ping()
                redis_ok = True
            except Exception:
                redis_ok = False

        self.operating_successfully(
            StatusResponseData(
                name=get_settings().APP_NAME,
                server=True,
                database=database_ok,
                redis=redis_ok,
            )
        )
