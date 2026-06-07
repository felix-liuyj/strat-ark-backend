"""用户中心域 ORM 模型与枚举：平台 API Key / 第三方账号绑定 / 活跃会话。

与前端 ``UserCenterPage`` 三块对齐：programmatic access（API Key）、connected
accounts（OAuth 绑定）、active sessions（会话）。API Key 明文仅创建时返回一次，
入库仅存哈希与掩码展示串。
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "ApiKeyPermissionEnum",
    "OAuthBinding",
    "OAuthProviderEnum",
    "PlatformApiKey",
    "UserSession",
)


class ApiKeyPermissionEnum(StrEnum):
    """API Key 权限（与前端 只读 / 读写 对齐）。"""

    READ = "read"
    READ_WRITE = "read_write"


class OAuthProviderEnum(StrEnum):
    """第三方 OAuth 提供方（与前端 Connected Accounts 对齐）。"""

    GOOGLE = "google"
    MICROSOFT = "microsoft"
    GITHUB = "github"
    APPLE = "apple"


class PlatformApiKey(Base, TimestampMixin):
    """平台 API Key（编程访问凭证）。

    明文仅创建时返回一次；``key_hash`` 存哈希用于校验，``key_prefix`` 存掩码展示串
    （如 sk_live_····a91f）。撤销不删除记录，置 ``revoked_at`` 保留审计痕迹。
    """

    __tablename__ = "platform_api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # 哈希后的密钥（不可逆），校验时比对哈希。
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # 掩码展示串（前缀 + 圆点 + 尾 4 位）。
    key_prefix: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    permission: Mapped[ApiKeyPermissionEnum] = mapped_column(
        String(20), nullable=False, default=ApiKeyPermissionEnum.READ
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OAuthBinding(Base, TimestampMixin):
    """第三方账号绑定（每用户 + 提供方一条）。

    ``linked_at`` 为首次绑定时间（不可变），解绑置 ``unbound`` 并清空标识；重新绑定
    刷新 ``linked_at``。同一用户多 provider 各占一条。
    """

    __tablename__ = "oauth_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[OAuthProviderEnum] = mapped_column(String(20), nullable=False, index=True)
    bound: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 第三方账号标识（邮箱 / 用户名 / sub），解绑后清空。
    account_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserSession(Base, TimestampMixin):
    """活跃会话（登录设备）。

    ``current`` 标记当前设备（无退出按钮）；退出会话置 ``active=False`` 保留记录，
    或由"退出全部"批量失效非当前会话。
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    device: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # 设备类型：desktop / mobile（前端据此选图标）。
    device_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="desktop")
    location: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
