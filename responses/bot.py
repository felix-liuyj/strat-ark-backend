"""交易机器人响应模型（camelCase）。

字段形状对齐前端 Bots 列表 / Bot Detail 各 tab：列表行、详情、生命周期操作、
实盘开启、交易记录、持仓、日志、AI 摘要、风控状态。
"""

from pydantic import Field

from libs.schema import ApiResponseModel
from models.bot import BotRunModeEnum, BotStatusEnum, BotTradeModeEnum

__all__ = (
    "BotAiSummaryResponseData",
    "BotDetailResponseData",
    "BotLifecycleResponseData",
    "BotListItemResponseData",
    "BotLiveEnableResponseData",
    "BotLogEntryResponseData",
    "BotPositionResponseData",
    "BotRiskRowResponseData",
    "BotRiskStatusResponseData",
    "BotSignalAlignmentResponseData",
    "BotTradeResponseData",
)


class BotListItemResponseData(ApiResponseModel):
    id: int = Field(..., description="机器人 ID")
    name: str = Field(..., description="机器人名称")
    subtitle: str = Field(..., description="副标题：周期 · 最大持仓数")
    tradeMode: BotTradeModeEnum = Field(..., description="交易模式")
    runMode: BotRunModeEnum = Field(..., description="运行模式")
    runModeLabel: str = Field(..., description="运行模式展示文案，例如 Dry-run")
    status: BotStatusEnum = Field(..., description="运行状态")
    strategyName: str = Field(..., description="策略名称")
    exchangeName: str = Field(..., description="交易所账户名称")
    todayPnlPct: float = Field(..., description="今日收益百分比")
    todayPnlLabel: str = Field(..., description="今日收益文案，例如 +2.3%")
    pnlPositive: bool = Field(..., description="今日收益是否为正")
    positions: int = Field(..., description="当前持仓数")


class BotDetailResponseData(BotListItemResponseData):
    exchangeAccountId: int = Field(..., description="交易所账户 ID")
    strategyId: int = Field(..., description="策略 ID")
    pairs: list[str] = Field(..., description="交易对列表")
    stakeCurrency: str = Field(..., description="计价币种")
    stakeAmount: float = Field(..., description="单笔仓位金额")
    maxOpenTrades: int = Field(..., description="最大持仓数")
    timeframe: str = Field(..., description="周期")
    stoploss: str = Field(..., description="止损")
    trailingStop: str = Field(..., description="移动止损")
    dailyLossLimit: str = Field(..., description="单日最大亏损")
    maxDrawdownLimit: str = Field(..., description="最大回撤")
    maxPosition: str = Field(..., description="单笔最大仓位")
    maxLeverage: str = Field(..., description="最大杠杆")
    riskConfig: dict[str, bool] = Field(..., description="风控开关")
    telegramNotify: bool = Field(..., description="Telegram 通知")
    autoStopOnError: bool = Field(..., description="异常自动停机")
    aiSignalFilter: bool = Field(..., description="AI 信号过滤")
    liveEnabled: bool = Field(..., description="是否已允许实盘")
    containerRef: str | None = Field(None, description="运行时容器引用")


class BotLifecycleResponseData(ApiResponseModel):
    id: int = Field(..., description="机器人 ID")
    status: BotStatusEnum = Field(..., description="操作后状态")
    runtimeStatus: str = Field(..., description="容器运行时状态")
    containerRef: str = Field(..., description="容器引用")
    message: str = Field(..., description="结果文案")


class BotLiveEnableResponseData(ApiResponseModel):
    id: int = Field(..., description="机器人 ID")
    liveEnabled: bool = Field(..., description="是否已允许实盘")
    runMode: BotRunModeEnum = Field(..., description="当前运行模式")
    message: str = Field(..., description="结果文案（需强确认 + 风控 + 2FA）")


class BotTradeResponseData(ApiResponseModel):
    pair: str = Field(..., description="交易对")
    side: str = Field(..., description="方向：long / short")
    openPrice: float = Field(..., description="开仓价")
    closePrice: float = Field(..., description="平仓价")
    amount: float = Field(..., description="数量")
    pnlAmount: float = Field(..., description="盈亏金额")
    pnlPct: float = Field(..., description="盈亏百分比")
    openedAt: str = Field(..., description="开仓时间")
    closedAt: str = Field(..., description="平仓时间")
    duration: str = Field(..., description="持仓时长")


class BotPositionResponseData(ApiResponseModel):
    pair: str = Field(..., description="交易对")
    side: str = Field(..., description="方向")
    openPrice: float = Field(..., description="开仓价")
    currentPrice: float = Field(..., description="当前价")
    amount: float = Field(..., description="数量")
    valueUsdt: float = Field(..., description="价值（USDT）")
    unrealizedPnlAmount: float = Field(..., description="未实现盈亏金额")
    unrealizedPnlPct: float = Field(..., description="未实现盈亏百分比")
    stopLossPrice: float = Field(..., description="止损价")


class BotLogEntryResponseData(ApiResponseModel):
    timestamp: str = Field(..., description="时间")
    level: str = Field(..., description="级别：INFO / TRADE / WARN / ERROR")
    message: str = Field(..., description="日志内容")


class BotSignalAlignmentResponseData(ApiResponseModel):
    aiRecommendation: str = Field(..., description="AI 综合建议")
    aiConfidence: float = Field(..., description="AI 置信度")
    strategySignal: str = Field(..., description="策略信号")
    botDirection: str = Field(..., description="Bot 当前方向")
    aligned: bool = Field(..., description="是否一致")
    riskLevel: str = Field(..., description="风险等级")
    suggestedAction: str = Field(..., description="建议动作")


class BotAiSummaryResponseData(ApiResponseModel):
    trend: str = Field(..., description="趋势判断，例如 Trend ↑")
    headline: str = Field(..., description="一句话结论")
    narrative: str = Field(..., description="投研摘要正文")
    alignment: BotSignalAlignmentResponseData = Field(..., description="信号一致性")


class BotRiskRowResponseData(ApiResponseModel):
    label: str = Field(..., description="风控项 i18n key")
    valuePct: float = Field(..., description="当前占用百分比（用于进度条宽度）")
    valueLabel: str = Field(..., description="展示值，例如 1.2% / 3%")
    safe: bool = Field(..., description="是否处于安全区间")


class BotRiskStatusResponseData(ApiResponseModel):
    overall: str = Field(..., description="总体状态：Normal / Warning / Critical")
    rows: list[BotRiskRowResponseData] = Field(..., description="各风控项明细")
