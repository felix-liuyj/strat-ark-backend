"""风控中心响应数据模型。

覆盖风险总览（总体状态 + 关键指标）、分层卡、风控规则、触发记录，与前端
RiskCenterPage 的总览卡 / 分层九宫格 / 规则列表 / 事件列表数据形状对齐。
"""

from pydantic import Field

from libs.schema import ApiResponseModel
from models.risk import RiskEventLevelEnum, RiskRuleScopeEnum, RiskRuleTypeEnum

__all__ = (
    "RiskEventResponseData",
    "RiskLevelCardResponseData",
    "RiskMetricResponseData",
    "RiskOverviewResponseData",
    "RiskRuleResponseData",
)


class RiskMetricResponseData(ApiResponseModel):
    key: str = Field(..., description="指标键，如 daily_loss")
    label: str = Field(..., description="指标展示名")
    current: float = Field(..., description="当前值")
    limit: float = Field(..., description="限额值")
    unit: str = Field(..., description="单位")


class RiskOverviewResponseData(ApiResponseModel):
    overallStatus: str = Field(..., description="总体风险状态，如 normal")
    pendingAlerts: int = Field(..., description="待处理告警数")
    metrics: list[RiskMetricResponseData] = Field(..., description="关键指标列表")


class RiskLevelCardResponseData(ApiResponseModel):
    scope: RiskRuleScopeEnum = Field(..., description="风控分层")
    title: str = Field(..., description="分层标题")
    subtitle: str = Field(..., description="分层副标题")
    status: str = Field(..., description="该层状态：run 正常 / warn 关注")
    statusLabel: str = Field(..., description="状态文案")


class RiskRuleResponseData(ApiResponseModel):
    id: int = Field(..., description="规则 ID")
    scope: RiskRuleScopeEnum = Field(..., description="风控分层")
    ruleType: RiskRuleTypeEnum = Field(..., description="规则类型")
    label: str = Field(..., description="规则展示名")
    currentValue: float | None = Field(None, description="当前值")
    limitValue: float | None = Field(None, description="限额值")
    unit: str = Field(..., description="单位")
    enabled: bool = Field(..., description="是否启用")
    botId: int | None = Field(None, description="绑定 Bot ID")
    strategyId: int | None = Field(None, description="绑定策略 ID")
    symbol: str | None = Field(None, description="绑定交易对")
    description: str = Field(..., description="规则说明")


class RiskEventResponseData(ApiResponseModel):
    id: int = Field(..., description="事件 ID")
    level: RiskEventLevelEnum = Field(..., description="事件级别")
    scope: RiskRuleScopeEnum = Field(..., description="所属分层")
    ruleType: RiskRuleTypeEnum | None = Field(None, description="触发的规则类型")
    title: str = Field(..., description="事件标题")
    description: str = Field(..., description="事件描述")
    symbol: str | None = Field(None, description="关联交易对")
    actionTaken: str | None = Field(None, description="处置动作")
    resolved: bool = Field(..., description="是否已处理")
    occurredAt: str = Field(..., description="发生时间文案")
