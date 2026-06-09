"""引擎管理响应模型（管理员专属）。"""

from datetime import datetime
from typing import Any

from pydantic import Field

from libs.schema import ApiResponseModel
from models.engine import EngineKindEnum, EngineOpStatusEnum, EngineOpTypeEnum, EngineStatusEnum

__all__ = (
    "DependencyResponseData",
    "EngineConnectionResponseData",
    "EngineDeploymentResponseData",
    "EngineLogResponseData",
    "EngineMonitorResponseData",
    "EngineOpResponseData",
    "EngineResponseData",
)


class EngineResponseData(ApiResponseModel):
    """引擎摘要（列表 / 顶部状态条）。"""

    id: int = Field(..., description="引擎 ID")
    engineKind: EngineKindEnum = Field(..., description="引擎类型")
    name: str = Field(..., description="引擎名称")
    status: EngineStatusEnum = Field(..., description="运行状态")


class DependencyResponseData(ApiResponseModel):
    name: str = Field(..., description="依赖名称")
    kind: str = Field(..., description="依赖类型")
    status: str = Field(..., description="健康状态")
    latency: str | None = Field(None, description="延迟 / 备注")


class EngineLogResponseData(ApiResponseModel):
    timestamp: datetime = Field(..., description="日志时间")
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志内容")


class EngineMonitorResponseData(ApiResponseModel):
    """引擎监控聚合（服务连接视图：连接 + 运营指标 + 依赖 + 日志）。"""

    engineKind: EngineKindEnum = Field(..., description="引擎类型")
    runtimeStatus: str = Field(..., description="运行时状态（running / degraded / unknown）")
    connected: bool = Field(..., description="serviceUrl 是否可达")
    serviceUrl: str = Field(..., description="引擎暴露的服务地址")
    latencyMs: float | None = Field(None, description="连接延迟（毫秒，不可达为空）")
    queueDepth: int = Field(..., description="队列深度")
    errorRate: str = Field(..., description="错误率")
    syncedAt: datetime = Field(..., description="数据同步时间")
    metrics: list[dict[str, str]] = Field(..., description="关键指标卡")
    dependencies: list[DependencyResponseData] = Field(..., description="外部依赖健康度")
    logs: list[EngineLogResponseData] = Field(..., description="近期日志")


class EngineConnectionResponseData(ApiResponseModel):
    """引擎连接配置（敏感字段已掩码）。"""

    engineKind: EngineKindEnum = Field(..., description="引擎类型")
    config: dict[str, Any] = Field(..., description="连接配置（敏感字段已掩码）")


class EngineDeploymentResponseData(ApiResponseModel):
    """引擎运行设置（非 k8s：日志级别 / 并发 / 模型参数等）。"""

    engineKind: EngineKindEnum = Field(..., description="引擎类型")
    config: dict[str, Any] = Field(..., description="引擎运行设置")


class EngineOpResponseData(ApiResponseModel):
    """引擎运维操作记录 / 结果。"""

    id: int = Field(..., description="运维记录 ID")
    engineKind: EngineKindEnum = Field(..., description="引擎类型")
    opType: EngineOpTypeEnum = Field(..., description="操作类型")
    status: EngineOpStatusEnum = Field(..., description="操作结果")
    message: str = Field(..., description="结果说明")
    operatorId: str | None = Field(None, description="操作者 ID")
    detail: dict[str, Any] = Field(..., description="操作参数与结果明细")
    createdAt: datetime = Field(..., description="操作时间")
