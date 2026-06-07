"""策略响应模型（camelCase）。

字段形状对齐前端 StrategyLabPage：列表项 + 详情（指标 / 参数 / 标签 / 版本 / 源码）。
"""

from pydantic import Field

from libs.schema import ApiResponseModel
from models.strategy import StrategyRiskEnum, StrategyStatusEnum, StrategyTypeEnum

__all__ = (
    "StrategyBacktestSubmitResponseData",
    "StrategyDetailResponseData",
    "StrategyListItemResponseData",
    "StrategyVersionResponseData",
)


class StrategyListItemResponseData(ApiResponseModel):
    id: int = Field(..., description="策略 ID")
    name: str = Field(..., description="策略名称")
    strategyType: StrategyTypeEnum = Field(..., description="策略类型")
    typeLabel: str = Field(..., description="类型展示文案，例如 趋势跟踪")
    icon: str = Field(..., description="图标标识")
    iconColor: str = Field(..., description="图标底色类")
    timeframe: str = Field(..., description="周期")
    market: str = Field(..., description="适用市场")
    risk: StrategyRiskEnum = Field(..., description="风险等级")
    riskLabel: str = Field(..., description="风险展示文案：高 / 中 / 低")
    status: StrategyStatusEnum = Field(..., description="状态")
    statusLabel: str = Field(..., description="状态展示文案：可用 / 测试中")
    backtestReturn: str = Field(..., description="回测收益文案")
    maxDrawdown: str = Field(..., description="最大回撤文案")
    isBuiltin: bool = Field(..., description="是否平台内置策略")


class StrategyVersionResponseData(ApiResponseModel):
    id: int = Field(..., description="版本记录 ID")
    version: str = Field(..., description="版本号")
    isCurrent: bool = Field(..., description="是否当前版本")
    changelog: str = Field(..., description="变更说明")
    createdAt: str = Field(..., description="创建时间")


class StrategyDetailResponseData(StrategyListItemResponseData):
    winRate: str = Field(..., description="胜率文案")
    sharpe: str = Field(..., description="夏普比率文案")
    equityCurve: str = Field(..., description="回测权益曲线 SVG path d")
    params: list[list[str]] = Field(..., description="有序参数键值对列表")
    tags: list[str] = Field(..., description="风险标签")
    sourceCode: str = Field(..., description="源码预览")
    description: str = Field(..., description="策略描述")
    versions: list[StrategyVersionResponseData] = Field(..., description="版本记录")


class StrategyBacktestSubmitResponseData(ApiResponseModel):
    """回测入口占位结果（真实回测属 backtests 域）。"""

    taskId: str = Field(..., description="回测任务 ID（占位）")
    strategyId: int = Field(..., description="策略 ID")
    status: str = Field(..., description="任务状态：queued / running")
    message: str = Field(..., description="提交结果文案")
