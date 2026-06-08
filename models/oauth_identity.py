"""OAuth identity mapping for login providers."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = ("OAuthIdentity",)


class OAuthIdentity(Base, TimestampMixin):
    """Provider subject 到本地用户的唯一映射。

    用户邮箱可能与已有密码账号重复，登录链路不能隐式按邮箱合并；因此 OAuth 登录只信任
    provider + subject 的稳定映射。
    """

    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_oauth_identities_provider_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    profile_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_claims: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    linked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
