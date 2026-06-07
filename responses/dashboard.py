"""Dashboard 响应模型。"""

from pydantic import Field

from libs.schema import ApiResponseModel

__all__ = (
    "DashboardAiSummaryResponseData",
    "DashboardBotResponseData",
    "DashboardMetricResponseData",
    "DashboardOverviewResponseData",
    "DashboardPositionResponseData",
    "DashboardRiskLimitResponseData",
    "DashboardRiskStatusResponseData",
    "DashboardSignalResponseData",
    "DashboardTopbarResponseData",
)


class DashboardTopbarResponseData(ApiResponseModel):
    """顶部状态栏数据。"""

    totalEquity: float = Field(..., description="总权益数值")
    totalEquityLabel: str = Field(..., description="总权益展示文案")
    todayPnlPct: float = Field(..., description="今日盈亏百分比")
    todayPnlLabel: str = Field(..., description="今日盈亏展示文案")
    mode: str = Field(..., description="账户模式：dry / live")
    unreadNotifications: int = Field(..., description="未读通知数量")


class DashboardRiskLimitResponseData(ApiResponseModel):
    """风控限制项。"""

    key: str = Field(..., description="风控项 key")
    labelKey: str = Field(..., description="前端 i18n label key")
    currentLabel: str = Field(..., description="当前值展示")
    limitLabel: str = Field(..., description="限制值展示")
    safe: bool = Field(..., description="是否处于安全阈值内")


class DashboardRiskStatusResponseData(ApiResponseModel):
    """Dashboard 风控横幅。"""

    status: str = Field(..., description="风控状态")
    headlineKey: str = Field(..., description="标题 i18n key")
    statusKey: str = Field(..., description="状态 i18n key")
    limits: list[DashboardRiskLimitResponseData] = Field(..., description="风控限制项")


class DashboardMetricResponseData(ApiResponseModel):
    """Dashboard KPI 指标卡。"""

    key: str = Field(..., description="指标 key")
    labelKey: str = Field(..., description="前端 i18n label key")
    value: float = Field(..., description="指标数值")
    valueLabel: str = Field(..., description="展示值")
    changeLabel: str = Field(..., description="变化文案")
    tone: str = Field(..., description="展示色调：brand / positive / warn / muted")
    sparkline: list[float] = Field(..., description="迷你趋势线数据")


class DashboardAiSummaryResponseData(ApiResponseModel):
    """AI 市场概要。"""

    bias: str = Field(..., description="市场倾向")
    confidencePct: int = Field(..., description="置信度百分比")
    updatedLabel: str = Field(..., description="更新时间展示")
    summary: str = Field(..., description="概要正文")
    focusSymbols: list[str] = Field(..., description="关注交易对")


class DashboardBotResponseData(ApiResponseModel):
    """Dashboard Bot 摘要。"""

    id: str = Field(..., description="Bot 业务 id")
    icon: str = Field(..., description="图标类型")
    name: str = Field(..., description="Bot 名称")
    subtitle: str = Field(..., description="策略 / 交易所 / 周期")
    status: str = Field(..., description="状态")
    pnlLabel: str = Field(..., description="收益展示")
    positionsLabelKey: str = Field(..., description="持仓展示 i18n key")


class DashboardSignalResponseData(ApiResponseModel):
    """Dashboard 信号行。"""

    id: str = Field(..., description="信号 id")
    time: str = Field(..., description="生成时间展示")
    symbol: str = Field(..., description="交易对")
    direction: str = Field(..., description="方向")
    source: str = Field(..., description="来源")
    confidenceLabel: str = Field(..., description="置信度展示")
    riskLevelKey: str = Field(..., description="风险等级 i18n key")
    status: str = Field(..., description="状态")


class DashboardPositionResponseData(ApiResponseModel):
    """Dashboard 持仓行。"""

    symbol: str = Field(..., description="交易对")
    direction: str = Field(..., description="方向")
    entryPriceLabel: str = Field(..., description="入场价展示")
    markPriceLabel: str = Field(..., description="标记价展示")
    sizeLabel: str = Field(..., description="数量展示")
    valueLabel: str = Field(..., description="持仓价值展示")
    pnlLabel: str = Field(..., description="浮动盈亏展示")
    botName: str = Field(..., description="来源 Bot")


class DashboardOverviewResponseData(ApiResponseModel):
    """Dashboard 页面聚合数据。"""

    topbar: DashboardTopbarResponseData = Field(..., description="顶部状态栏")
    risk: DashboardRiskStatusResponseData = Field(..., description="风控状态")
    metrics: list[DashboardMetricResponseData] = Field(..., description="KPI 指标卡")
    aiSummary: DashboardAiSummaryResponseData = Field(..., description="AI 市场概要")
    bots: list[DashboardBotResponseData] = Field(..., description="Bot 摘要")
    signals: list[DashboardSignalResponseData] = Field(..., description="最新信号")
    positions: list[DashboardPositionResponseData] = Field(..., description="当前持仓")
