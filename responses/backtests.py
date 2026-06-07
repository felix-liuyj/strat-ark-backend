"""回测中心响应数据模型。"""

from pydantic import Field

from libs.schema import ApiResponseModel
from models.backtests import BacktestStatusEnum

__all__ = (
    "AgentOpinionData",
    "BacktestAiReviewData",
    "BacktestDetailData",
    "BacktestMetricsData",
    "BacktestResultData",
    "BacktestSeriesData",
    "BacktestTaskData",
    "DailyReturnPointData",
    "DrawdownPointData",
    "EquityPointData",
    "PairReturnData",
)


class BacktestTaskData(ApiResponseModel):
    """回测任务摘要（任务列表行）。"""

    id: int = Field(..., description="任务 ID")
    strategyName: str = Field(..., description="策略名称")
    symbol: str = Field(..., description="交易对")
    timeframe: str = Field(..., description="周期")
    startDate: str = Field(..., description="开始日期")
    endDate: str = Field(..., description="结束日期")
    status: BacktestStatusEnum = Field(..., description="任务状态")
    totalReturn: float | None = Field(None, description="总收益（%）")
    maxDrawdown: float | None = Field(None, description="最大回撤（%）")
    sharpe: float | None = Field(None, description="夏普比率")


class BacktestMetricsData(ApiResponseModel):
    """绩效指标（结果页指标卡）。"""

    totalReturn: float = Field(..., description="总收益（%）")
    cagr: float = Field(..., description="年化收益（%）")
    maxDrawdown: float = Field(..., description="最大回撤（%）")
    sharpe: float = Field(..., description="夏普比率")
    winRate: float = Field(..., description="胜率（%）")
    profitFactor: float = Field(..., description="盈亏比")
    avgDurationHours: float = Field(..., description="平均持仓时长（小时）")
    trades: int = Field(..., description="交易次数")
    bestPair: str = Field(..., description="最佳交易对")
    worstPair: str = Field(..., description="最差交易对")
    finalBalance: float = Field(..., description="期末权益（USDT）")


class EquityPointData(ApiResponseModel):
    x: int = Field(..., description="序号")
    value: float = Field(..., description="账户净值")


class DrawdownPointData(ApiResponseModel):
    x: int = Field(..., description="序号")
    value: float = Field(..., description="回撤百分比（负值）")


class DailyReturnPointData(ApiResponseModel):
    day: int = Field(..., description="交易日序号")
    value: float = Field(..., description="当日收益（%）")


class PairReturnData(ApiResponseModel):
    name: str = Field(..., description="交易对")
    value: float = Field(..., description="累计收益（%）")


class BacktestSeriesData(ApiResponseModel):
    """结果各序列（权益曲线 / 回撤 / 每日收益 / 交易对归因）。"""

    equityCurve: list[EquityPointData] = Field(default_factory=list, description="权益曲线")
    drawdownCurve: list[DrawdownPointData] = Field(default_factory=list, description="回撤曲线")
    dailyReturns: list[DailyReturnPointData] = Field(default_factory=list, description="每日收益热力图")
    pairReturns: list[PairReturnData] = Field(default_factory=list, description="交易对收益归因")


class AgentOpinionData(ApiResponseModel):
    """单个 Agent 观点（AI 复盘内嵌）。"""

    role: str = Field(..., description="Agent 角色")
    name: str = Field(..., description="Agent 名称")
    stance: str = Field(..., description="立场")
    summary: str = Field(..., description="观点摘要")
    points: list[str] = Field(default_factory=list, description="要点列表")


class BacktestAiReviewData(ApiResponseModel):
    """AI 回测复盘结论。"""

    verdict: str = Field(..., description="结论")
    strength: str = Field(..., description="优势")
    weakness: str = Field(..., description="弱点")
    suggestion: str = Field(..., description="建议")
    summary: str = Field(..., description="复盘摘要")
    agents: list[AgentOpinionData] = Field(default_factory=list, description="参与复盘的 Agent 观点")


class BacktestDetailData(ApiResponseModel):
    """回测任务详情（任务信息 + 指标 + 序列 + AI 复盘）。"""

    task: BacktestTaskData = Field(..., description="任务摘要")
    metrics: BacktestMetricsData | None = Field(None, description="绩效指标（完成后有值）")
    series: BacktestSeriesData | None = Field(None, description="结果序列（完成后有值）")
    aiReview: BacktestAiReviewData | None = Field(None, description="AI 复盘（生成后有值）")


class BacktestResultData(ApiResponseModel):
    """回测结果（任务信息 + 指标 + 序列，不含 AI 复盘）。"""

    task: BacktestTaskData = Field(..., description="任务摘要")
    metrics: BacktestMetricsData | None = Field(None, description="绩效指标（完成后有值）")
    series: BacktestSeriesData | None = Field(None, description="结果序列（完成后有值）")
