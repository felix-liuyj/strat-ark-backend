"""引擎与引擎运维记录 ORM 模型（管理员专属）。

- ``Engine`` 引擎注册表（Freqtrade 执行引擎 / TradingAgents 投研引擎），含连接配置与
  部署配置（JSON，敏感凭证掩码后回显）。
- ``EngineOp`` 引擎运维操作流水（restart / reload / drain / clear_queue /
  emergency_stop / tear_down），危险操作同时写平台审计日志。
"""

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin
from libs.secure_config import ENGINE_SENSITIVE_CONFIG_KEYS, decrypt_sensitive_config

__all__ = (
    "Engine",
    "EngineKindEnum",
    "EngineOp",
    "EngineOpStatusEnum",
    "EngineOpTypeEnum",
    "EngineStatusEnum",
    "get_engine_connection_config",
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
    """引擎运维操作类型（经引擎暴露的控制 API；服务连接模型，无 k8s 副本 / 镜像概念）。"""

    TEST_CONNECTION = "test_connection"
    RESTART = "restart"
    RELOAD = "reload"
    DRAIN = "drain"
    CLEAR_QUEUE = "clear_queue"
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

    引擎不做 k8s 集群化，作为独立服务运行；backend 经 ``connection_config.serviceUrl``
    暴露的 HTTP API 做服务连接交互。``connection_config`` 存服务连接（serviceUrl / token /
    timeout / 网关等），``deployment_config`` 存引擎运行设置（日志级别 / 并发 / 模型参数等，
    非 k8s 编排 spec）；敏感字段（token / apiKey / secret）使用 Fernet 密文入库，响应不回显明文。
    """

    __tablename__ = "engines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engine_kind: Mapped[EngineKindEnum] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[EngineStatusEnum] = mapped_column(String(20), nullable=False, default=EngineStatusEnum.RUNNING)
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
    # 操作参数与结果明细（如操作下发时的附加上下文）。
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


async def get_engine_connection_config(db: AsyncSession, kind: EngineKindEnum) -> dict[str, Any] | None:
    """读取指定引擎的连接配置（管理员经引擎管理页落库）；引擎未注册返回 None。

    供业务域（AI 投研等）取管理员配置的网关 / 服务地址；缺失字段由调用方回退 env。
    """
    engine = await db.scalar(select(Engine).where(Engine.engine_kind == kind))
    if engine is None:
        return None
    return decrypt_sensitive_config(engine.connection_config or {}, ENGINE_SENSITIVE_CONFIG_KEYS)
