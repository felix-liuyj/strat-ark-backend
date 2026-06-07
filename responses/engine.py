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
    "PodResponseData",
    "ResourceUsageResponseData",
)


class EngineResponseData(ApiResponseModel):
    """引擎摘要（列表 / 顶部状态条）。"""

    id: int = Field(..., description="引擎 ID")
    engineKind: EngineKindEnum = Field(..., description="引擎类型")
    name: str = Field(..., description="引擎名称")
    namespace: str = Field(..., description="K8s 命名空间")
    deploymentName: str = Field(..., description="Deployment 名称")
    status: EngineStatusEnum = Field(..., description="运行状态")
    replicasDesired: int = Field(..., description="期望副本数")


class PodResponseData(ApiResponseModel):
    name: str = Field(..., description="Pod 名称")
    node: str = Field(..., description="所在节点")
    status: str = Field(..., description="Pod 状态")
    cpu: str = Field(..., description="CPU 用量")
    mem: str = Field(..., description="内存用量")
    restarts: int = Field(..., description="重启次数")
    uptime: str = Field(..., description="运行时长")


class ResourceUsageResponseData(ApiResponseModel):
    label: str = Field(..., description="资源名称")
    percent: int = Field(..., description="使用百分比")
    value: str = Field(..., description="可读用量")


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
    """引擎监控聚合（Pods / 资源 / 依赖 / 日志 / 指标 + 运行时快照）。"""

    engineKind: EngineKindEnum = Field(..., description="引擎类型")
    runtimeStatus: str = Field(..., description="运行时状态")
    replicasReady: int = Field(..., description="就绪副本数")
    replicasDesired: int = Field(..., description="期望副本数")
    queueDepth: int = Field(..., description="队列深度")
    errorRate: str = Field(..., description="错误率")
    syncedAt: datetime = Field(..., description="数据同步时间")
    metrics: list[dict[str, str]] = Field(..., description="关键指标卡")
    pods: list[PodResponseData] = Field(..., description="Pod 列表")
    resources: list[ResourceUsageResponseData] = Field(..., description="资源用量")
    dependencies: list[DependencyResponseData] = Field(..., description="外部依赖健康度")
    logs: list[EngineLogResponseData] = Field(..., description="近期日志")


class EngineConnectionResponseData(ApiResponseModel):
    """引擎连接配置（敏感字段已掩码）。"""

    engineKind: EngineKindEnum = Field(..., description="引擎类型")
    config: dict[str, Any] = Field(..., description="连接配置（敏感字段已掩码）")


class EngineDeploymentResponseData(ApiResponseModel):
    """引擎部署配置。"""

    engineKind: EngineKindEnum = Field(..., description="引擎类型")
    replicasDesired: int = Field(..., description="期望副本数")
    config: dict[str, Any] = Field(..., description="部署配置")


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
