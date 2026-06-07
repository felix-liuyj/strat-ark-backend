"""平台审计日志模型与枚举（append-only + 链式签名）。"""

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "ActorTypeEnum",
    "AuditActionEnum",
    "AuditCategoryEnum",
    "AuditLog",
    "AuditStatusEnum",
)


class AuditActionEnum(StrEnum):
    CREATE = "create"
    IMPORT = "import"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    LOGIN = "login"
    APPROVE = "approve"
    REJECT = "reject"
    EXECUTE = "execute"
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    DEPLOY = "deploy"
    EMERGENCY_STOP = "emergency_stop"
    SUBSCRIBE = "subscribe"
    CANCEL = "cancel"


class ActorTypeEnum(StrEnum):
    """操作者类型（与前端审计页 RoleKey 对齐：admin / system / user）。"""

    ADMIN = "admin"
    SYSTEM = "system"
    USER = "user"


class AuditCategoryEnum(StrEnum):
    """审计类别（前端审计页分类筛选）。"""

    AUTH = "auth"
    BOT = "bot"
    STRATEGY = "strategy"
    SIGNAL = "signal"
    RISK = "risk"
    ENGINE = "engine"
    EXCHANGE = "exchange"
    SUBSCRIPTION = "subscription"
    SETTINGS = "settings"
    SYSTEM = "system"


class AuditStatusEnum(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class AuditLog(TimestampMixin, Base):
    """平台级 append-only 审计日志。

    每条记录写入时基于上一条的 ``signature`` 计算本条 ``signature``（sha256 链），
    构成可校验、不可篡改的哈希链；任意中间记录被改动都会断链。
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="System")
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default=ActorTypeEnum.SYSTEM)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default=AuditCategoryEnum.SYSTEM, index=True)
    resource: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    message: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=AuditStatusEnum.SUCCESS)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    prev_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
