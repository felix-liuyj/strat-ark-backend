"""导航菜单聚合 ViewModel。"""

from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth.permissions import PermissionChecker
from models.bot import Bot, BotStatusEnum
from models.notification import Notification
from models.signals import Signal, SignalStatusEnum
from responses.navigation import NavigationCountsResponseData
from view_models.common.base import BaseViewModel

__all__ = ("GetNavigationCountsViewModel",)

_PENDING_SIGNAL_STATUSES = (SignalStatusEnum.GENERATED, SignalStatusEnum.REVIEWED)


class GetNavigationCountsViewModel(BaseViewModel):
    """侧边导航菜单计数聚合入口。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)
        self.operating_successfully(await _build_counts(self.db, user_id))


async def _build_counts(db: AsyncSession, user_id: int) -> NavigationCountsResponseData:
    return NavigationCountsResponseData(
        signals=await _count_pending_signals(db, user_id),
        bots=await _count_running_bots(db, user_id),
        notifications=await _count_unread_notifications(db, user_id),
    )


async def _count_rows(db: AsyncSession, model: Any, *where: Any) -> int:
    value = await db.scalar(select(func.count()).select_from(model).where(*where))
    return int(value or 0)


async def _count_pending_signals(db: AsyncSession, user_id: int) -> int:
    return await _count_rows(
        db,
        Signal,
        Signal.user_id == user_id,
        Signal.status.in_(_PENDING_SIGNAL_STATUSES),
    )


async def _count_running_bots(db: AsyncSession, user_id: int) -> int:
    return await _count_rows(db, Bot, Bot.user_id == user_id, Bot.status == BotStatusEnum.RUNNING)


async def _count_unread_notifications(db: AsyncSession, user_id: int) -> int:
    return await _count_rows(db, Notification, Notification.user_id == user_id, Notification.is_read.is_(False))
