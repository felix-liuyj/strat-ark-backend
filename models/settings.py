"""设置域 ORM 模型与枚举：系统配置 key-value（按分组）。

覆盖前端 SettingsPage 五个分组：General（偏好 + 行为）、LLM（模型网关 + 用量）、
Prompt（模板 CRUD）、Appearance（外观）、Data（数据导出 / 清除 / 审计保留）。

统一用单表 ``system_configs`` 承载，按 ``group`` + ``key`` 唯一定位，值存 JSON；
Prompt 模板亦作为 group=prompt 的多行配置存放（``key`` = 模板 id，``value`` = 模板内容）。
配置归属单个用户（``user_id``），实现每用户独立设置。
"""

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "SystemConfig",
    "SystemConfigGroupEnum",
)


class SystemConfigGroupEnum(StrEnum):
    """配置分组（与前端 Settings 五个 Tab 对齐）。"""

    GENERAL = "general"
    LLM = "llm"
    PROMPT = "prompt"
    APPEARANCE = "appearance"
    DATA = "data"


class SystemConfig(Base, TimestampMixin):
    """系统配置项（每用户 + 分组 + key 唯一）。

    ``value`` 为 JSON，可承载标量、对象或列表（Prompt 模板内容即对象）；
    敏感字段（如 LLM API Key）入库存明文但响应层掩码返回。
    """

    __tablename__ = "system_configs"
    __table_args__ = (UniqueConstraint("user_id", "group", "key", name="uq_system_config_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    group: Mapped[SystemConfigGroupEnum] = mapped_column(String(30), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
