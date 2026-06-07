"""引擎与引擎运维记录 ORM 模型（管理员专属）。

- ``Engine`` 引擎注册表（Freqtrade 执行引擎 / TradingAgents 投研引擎），含连接配置与
  部署配置（JSON，敏感凭证掩码后回显）。
- ``EngineOp`` 引擎运维操作流水（scale / restart / reload / drain / clear_queue /
  redeploy / emergency_stop / tear_down），危险操作同时写平台审计日志。
"""

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "Engine",
    "EngineKindEnum",
    "EngineOp",
    "EngineOpStatusEnum",
    "EngineOpTypeEnum",
    "EngineStatusEnum",
)


class EngineKindEnum(StrEnum):
    """引擎类型（与前端 EngineKey 对齐）。"""

    FREQTRADE = "freqtrade"
    TRADINGAGENTS = "tradingagents"


class EngineStatusEnum(StrEnum):
    """引擎运行状态。"""

    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    DEPLOYING = "deploying"


class EngineOpTypeEnum(StrEnum):
    """引擎运维操作类型（与前端高级操作 / 危险操作对齐）。"""

    TEST_CONNECTION = "test_connection"
    SCALE = "scale"
    RESTART = "restart"
    RELOAD = "reload"
    DRAIN = "drain"
    CLEAR_QUEUE = "clear_queue"
    REDEPLOY = "redeploy"
    EMERGENCY_STOP = "emergency_stop"
    TEAR_DOWN = "tear_down"


class EngineOpStatusEnum(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


# 触发后需要写平台审计日志的危险运维操作。
DANGEROUS_OP_TYPES: frozenset[EngineOpTypeEnum] = frozenset(
    {EngineOpTypeEnum.EMERGENCY_STOP, EngineOpTypeEnum.TEAR_DOWN}
)


class Engine(Base, TimestampMixin):
    """引擎注册表（管理员维护）。

    ``connection_config`` / ``deployment_config`` 按引擎类型存不同字段（如 service URL、
    REST token、镜像、副本、HPA、模型网关等）；敏感字段（token / apiKey / secret）入库前
    由 ViewModel 掩码或仅保留必要部分，回显时不返回明文。
    """

    __tablename__ = "engines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engine_kind: Mapped[EngineKindEnum] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    namespace: Mapped[str] = mapped_column(String(120), nullable=False, default="stratark-prod")
    deployment_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[EngineStatusEnum] = mapped_column(String(20), nullable=False, default=EngineStatusEnum.RUNNING)
    replicas_desired: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    connection_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    deployment_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class EngineOp(Base, TimestampMixin):
    """引擎运维操作流水。"""

    __tablename__ = "engine_ops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 引用 engines.id（跨记录引用用字符串 ForeignKey，不使用 ORM relationship）。
    engine_id: Mapped[int] = mapped_column(ForeignKey("engines.id"), index=True, nullable=False)
    engine_kind: Mapped[EngineKindEnum] = mapped_column(String(20), nullable=False, index=True)
    op_type: Mapped[EngineOpTypeEnum] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[EngineOpStatusEnum] = mapped_column(
        String(20), nullable=False, default=EngineOpStatusEnum.SUCCESS
    )
    message: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # 操作者（管理员）user id，便于回溯。
    operator_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 操作参数与结果明细（如 scale 的目标副本数、redeploy 的镜像标签）。
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
