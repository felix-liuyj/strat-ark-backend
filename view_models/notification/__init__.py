"""通知与通知渠道 view models。

覆盖：通知信息流、标记已读 / 全部已读、创建通知、渠道配置 CRUD（按渠道类型字段不同）、
渠道发送测试（调 notifier 真实发送能力）、事件 × 渠道订阅矩阵读写。
"""

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from forms.notification import (
    NotificationChannelCreateForm,
    NotificationChannelUpdateForm,
    NotificationCreateForm,
    NotificationSubscriptionUpdateForm,
)
from libs.auth.permissions import PermissionChecker
from libs.integrations import notifier
from libs.secure_config import (
    NOTIFICATION_SENSITIVE_CONFIG_KEYS,
    decrypt_sensitive_config,
    mask_sensitive_config,
    merge_sensitive_config,
)
from models.notification import (
    ChannelKindEnum,
    Notification,
    NotificationChannel,
    NotificationSubscription,
)
from responses.notification import (
    NotificationChannelResponseData,
    NotificationListResponseData,
    NotificationResponseData,
    NotificationSubscriptionResponseData,
    NotificationTestResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = (
    "CreateNotificationChannelViewModel",
    "CreateNotificationViewModel",
    "DeleteNotificationChannelViewModel",
    "GetNotificationSubscriptionsViewModel",
    "ListNotificationChannelsViewModel",
    "ListNotificationsViewModel",
    "MarkAllNotificationsReadViewModel",
    "MarkNotificationReadViewModel",
    "SendChannelTestViewModel",
    "UpdateNotificationChannelViewModel",
    "UpdateNotificationSubscriptionsViewModel",
)

_CHANNEL_ORDER = tuple(ChannelKindEnum)
_PRIVATE_SUBTITLE_KINDS = frozenset(
    {ChannelKindEnum.LARK, ChannelKindEnum.DISCORD, ChannelKindEnum.WEBHOOK}
)


def _channel_order_index(channel: NotificationChannel) -> int:
    try:
        return _CHANNEL_ORDER.index(channel.channel_kind)
    except ValueError:
        return len(_CHANNEL_ORDER)


def _safe_subtitle(kind: ChannelKindEnum, subtitle: str, config: dict[str, object]) -> str:
    if kind not in _PRIVATE_SUBTITLE_KINDS:
        return subtitle.strip()
    has_private_url = bool(config.get("url") or config.get("webhookUrl"))
    return "notif.chConfigured" if has_private_url else "notif.chUnbound"


def _build_notification(item: Notification) -> NotificationResponseData:
    return NotificationResponseData(
        id=item.id,
        notifType=item.notif_type,
        title=item.title,
        description=item.description,
        isRead=item.is_read,
        resource=item.resource,
        resourceId=item.resource_id,
        createdAt=item.created_at,
    )


def _build_channel(channel: NotificationChannel) -> NotificationChannelResponseData:
    return NotificationChannelResponseData(
        id=channel.id,
        channelKind=channel.channel_kind,
        displayName=channel.display_name,
        subtitle=channel.subtitle,
        isEnabled=channel.is_enabled,
        config=mask_sensitive_config(channel.config or {}, NOTIFICATION_SENSITIVE_CONFIG_KEYS),
    )


def _build_subscription(sub: NotificationSubscription) -> NotificationSubscriptionResponseData:
    return NotificationSubscriptionResponseData(
        eventKey=sub.event_key,
        channelKind=sub.channel_kind,
        isEnabled=sub.is_enabled,
    )


class ListNotificationsViewModel(BaseViewModel):
    """通知信息流（可按类型筛选 + 仅未读）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        notif_type: str | None,
        unread_only: bool,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker
        self.notif_type = notif_type
        self.unread_only = unread_only

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        stmt = select(Notification).where(Notification.user_id == user_id)
        if self.notif_type:
            stmt = stmt.where(Notification.notif_type == self.notif_type)
        if self.unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())

        items = (await self.db.scalars(stmt)).all()
        unread_total = await self.db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        self.operating_successfully(
            NotificationListResponseData(
                unreadCount=int(unread_total or 0),
                items=[_build_notification(item) for item in items],
            )
        )


class CreateNotificationViewModel(BaseViewModel):
    """创建一条站内通知（便于联调与系统触发）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: NotificationCreateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        title = self.form.title.strip()
        if not title:
            self.illegal_parameters("通知标题不能为空")
            return

        item = Notification(
            user_id=int(self.checker.user_id),
            notif_type=self.form.notifType,
            title=title,
            description=self.form.description.strip(),
            resource=self.form.resource,
            resource_id=self.form.resourceId,
            is_read=False,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        self.operating_successfully(_build_notification(item))


class MarkNotificationReadViewModel(BaseViewModel):
    """标记单条通知已读。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        notification_id: int,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.notification_id = notification_id
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        item = await self.db.get(Notification, self.notification_id)
        if item is None or item.user_id != int(self.checker.user_id):
            self.not_found("通知不存在或无权访问")
            return
        if item.is_read:
            self.nothing_changed()
            return
        item.is_read = True
        await self.db.commit()
        await self.db.refresh(item)
        self.operating_successfully(_build_notification(item))


class MarkAllNotificationsReadViewModel(BaseViewModel):
    """全部标记已读。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        result = await self.db.execute(
            update(Notification)
            .where(Notification.user_id == int(self.checker.user_id), Notification.is_read.is_(False))
            .values(is_read=True)
        )
        await self.db.commit()
        if not result.rowcount:
            self.nothing_changed()
            return
        self.operating_successfully({"updated": result.rowcount})


class ListNotificationChannelsViewModel(BaseViewModel):
    """渠道配置列表（敏感字段掩码）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        channels = (
            await self.db.scalars(
                select(NotificationChannel).where(NotificationChannel.user_id == int(self.checker.user_id))
            )
        ).all()
        channels = sorted(channels, key=_channel_order_index)
        self.operating_successfully([_build_channel(channel) for channel in channels])


class CreateNotificationChannelViewModel(BaseViewModel):
    """新增渠道配置（每用户每渠道类型唯一）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: NotificationChannelCreateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        existing = await self.db.scalar(
            select(NotificationChannel).where(
                NotificationChannel.user_id == user_id,
                NotificationChannel.channel_kind == self.form.channelKind,
            )
        )
        if existing is not None:
            self.illegal_parameters("该渠道类型已配置，请直接编辑")
            return

        stored_config = merge_sensitive_config({}, self.form.config, NOTIFICATION_SENSITIVE_CONFIG_KEYS)
        channel = NotificationChannel(
            user_id=user_id,
            channel_kind=self.form.channelKind,
            display_name=self.form.displayName.strip(),
            subtitle=_safe_subtitle(self.form.channelKind, self.form.subtitle, self.form.config),
            is_enabled=self.form.isEnabled,
            config=stored_config,
        )
        self.db.add(channel)
        await self.db.commit()
        await self.db.refresh(channel)
        self.operating_successfully(_build_channel(channel))


class UpdateNotificationChannelViewModel(BaseViewModel):
    """更新渠道配置（部分字段）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        channel_id: int,
        form: NotificationChannelUpdateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.channel_id = channel_id
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        channel = await self.db.get(NotificationChannel, self.channel_id)
        if channel is None or channel.user_id != int(self.checker.user_id):
            self.not_found("渠道配置不存在或无权访问")
            return

        if self.form.displayName is not None:
            channel.display_name = self.form.displayName.strip()
        if self.form.isEnabled is not None:
            channel.is_enabled = self.form.isEnabled
        if self.form.config is not None:
            channel.config = merge_sensitive_config(
                channel.config or {}, self.form.config, NOTIFICATION_SENSITIVE_CONFIG_KEYS
            )
        plain_config = decrypt_sensitive_config(channel.config or {}, NOTIFICATION_SENSITIVE_CONFIG_KEYS)
        if self.form.subtitle is not None:
            channel.subtitle = _safe_subtitle(channel.channel_kind, self.form.subtitle, plain_config)
        elif self.form.config is not None and channel.channel_kind in _PRIVATE_SUBTITLE_KINDS:
            channel.subtitle = _safe_subtitle(channel.channel_kind, channel.subtitle, plain_config)

        await self.db.commit()
        await self.db.refresh(channel)
        self.operating_successfully(_build_channel(channel))


class DeleteNotificationChannelViewModel(BaseViewModel):
    """删除渠道配置。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        channel_id: int,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.channel_id = channel_id
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        channel = await self.db.get(NotificationChannel, self.channel_id)
        if channel is None or channel.user_id != int(self.checker.user_id):
            self.not_found("渠道配置不存在或无权访问")
            return
        await self.db.delete(channel)
        await self.db.commit()
        self.operating_successfully({"deleted": self.channel_id})


class SendChannelTestViewModel(BaseViewModel):
    """发送渠道测试通知（调 notifier 真实发送能力）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        channel_id: int,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.channel_id = channel_id
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        channel = await self.db.get(NotificationChannel, self.channel_id)
        if channel is None or channel.user_id != int(self.checker.user_id):
            self.not_found("渠道配置不存在或无权访问")
            return

        config = decrypt_sensitive_config(channel.config or {}, NOTIFICATION_SENSITIVE_CONFIG_KEYS)
        result = notifier.send_test(str(channel.channel_kind), config)
        self.operating_successfully(
            NotificationTestResponseData(
                ok=result.ok,
                channelKind=channel.channel_kind,
                message=result.message,
                latencyMs=result.latency_ms,
            )
        )


class GetNotificationSubscriptionsViewModel(BaseViewModel):
    """读取事件 × 渠道订阅矩阵。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        subs = (
            await self.db.scalars(
                select(NotificationSubscription)
                .where(NotificationSubscription.user_id == int(self.checker.user_id))
                .order_by(NotificationSubscription.id.asc())
            )
        ).all()
        self.operating_successfully([_build_subscription(sub) for sub in subs])


class UpdateNotificationSubscriptionsViewModel(BaseViewModel):
    """批量 upsert 订阅矩阵单元格。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: NotificationSubscriptionUpdateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        existing = (
            await self.db.scalars(
                select(NotificationSubscription).where(NotificationSubscription.user_id == user_id)
            )
        ).all()
        index: dict[tuple[str, ChannelKindEnum], NotificationSubscription] = {
            (sub.event_key, sub.channel_kind): sub for sub in existing
        }

        for cell in self.form.items:
            key = (cell.eventKey, cell.channelKind)
            current = index.get(key)
            if current is None:
                self.db.add(
                    NotificationSubscription(
                        user_id=user_id,
                        event_key=cell.eventKey,
                        channel_kind=cell.channelKind,
                        is_enabled=cell.isEnabled,
                    )
                )
            else:
                current.is_enabled = cell.isEnabled

        await self.db.commit()
        self.operating_successfully({"updated": len(self.form.items)})
