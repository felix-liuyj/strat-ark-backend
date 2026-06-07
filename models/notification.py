"""通知与通知渠道 ORM 模型。

包含三类数据：
- ``Notification`` 通知信息流（每用户的站内通知，可标记已读）。
- ``NotificationChannel`` 渠道配置（每用户每渠道类型一条，含按类型不同的 JSON 配置）。
- ``NotificationSubscription`` 事件 × 渠道订阅矩阵（每用户对某事件类型在某渠道上的开关）。
"""

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "ChannelKindEnum",
    "Notification",
    "NotificationChannel",
    "NotificationSubscription",
    "NotificationTypeEnum",
)


class NotificationTypeEnum(StrEnum):
    """通知类型（与前端 NotifType 对齐：trade / risk / alert / bot / ai）。"""

    TRADE = "trade"
    RISK = "risk"
    ALERT = "alert"
    BOT = "bot"
    AI = "ai"


class ChannelKindEnum(StrEnum):
    """渠道类型（与前端 ChannelKind 对齐，并补充 slack / sms / apppush）。"""

    WEB = "web"
    EMAIL = "email"
    TELEGRAM = "telegram"
    LARK = "lark"
    SLACK = "slack"
    DISCORD = "discord"
    WEBHOOK = "webhook"
    SMS = "sms"
    APPPUSH = "apppush"


class Notification(Base, TimestampMixin):
    """站内通知信息流。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    notif_type: Mapped[NotificationTypeEnum] = mapped_column(
        String(20), nullable=False, default=NotificationTypeEnum.ALERT, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    # 业务关联资源（如订单 / 信号 / Bot 等）的轻量引用，便于前端跳转。
    resource: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)


class NotificationChannel(Base, TimestampMixin):
    """每用户每渠道类型一条配置。

    ``config`` 按渠道类型存不同字段（敏感字段如 botToken / secret 入库前由 ViewModel
    掩码或仅保留必要部分），如:
    - email: ``{"inbox": "...", "frequency": "realtime", "digestTime": "09:00"}``
    - telegram: ``{"botToken": "...", "chatId": "...", "format": "compact"}``
    - webhook: ``{"url": "...", "method": "POST", "contentType": "...", "secret": "..."}``
    """

    __tablename__ = "notification_channels"
    __table_args__ = (UniqueConstraint("user_id", "channel_kind", name="uq_notif_channel_user_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    channel_kind: Mapped[ChannelKindEnum] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # 渠道副标题 / 绑定标识（如邮箱地址、@handle、未绑定提示）。
    subtitle: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class NotificationSubscription(Base, TimestampMixin):
    """事件 × 渠道订阅矩阵：用户对某事件类型在某渠道上的开关。"""

    __tablename__ = "notification_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "event_key", "channel_kind", name="uq_notif_sub_user_event_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # 事件标识（如 bot_lifecycle / new_signal / order_filled / stop_loss 等）。
    event_key: Mapped[str] = mapped_column(String(60), nullable=False)
    channel_kind: Mapped[ChannelKindEnum] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
