"""交易记录响应数据模型。

覆盖交易记录行、持仓快照、未完成订单、交易统计 KPI 与 CSV 导出，与前端 TradesPage
的指标卡 / 表格、持仓列表、未完成订单数据形状对齐。
"""

from pydantic import Field

from libs.schema import ApiResponseModel
from models.trade import OrderStatusEnum, OrderTypeEnum, TradeSideEnum, TradeStatusEnum

__all__ = (
    "OpenOrderResponseData",
    "PositionResponseData",
    "TradeExportResponseData",
    "TradeResponseData",
    "TradeStatsResponseData",
)


class TradeResponseData(ApiResponseModel):
    tradeRef: str = Field(..., description="交易引用号")
    openedAt: str = Field(..., description="开仓时间文案")
    symbol: str = Field(..., description="交易对")
    side: TradeSideEnum = Field(..., description="方向")
    botName: str = Field(..., description="所属 Bot")
    openPrice: float = Field(..., description="开仓价")
    closePrice: float | None = Field(None, description="平仓价（持仓中为空）")
    quantity: float = Field(..., description="数量")
    pnl: float = Field(..., description="盈亏金额")
    pnlPct: float = Field(..., description="盈亏百分比")
    duration: str = Field(..., description="时长文案")
    status: TradeStatusEnum = Field(..., description="状态")


class PositionResponseData(ApiResponseModel):
    positionRef: str = Field(..., description="持仓引用号")
    symbol: str = Field(..., description="交易对")
    side: TradeSideEnum = Field(..., description="方向")
    botName: str = Field(..., description="所属 Bot")
    openPrice: float = Field(..., description="开仓价")
    currentPrice: float = Field(..., description="当前价")
    quantity: float = Field(..., description="数量")
    positionValue: float = Field(..., description="持仓价值")
    unrealizedPnl: float = Field(..., description="未实现盈亏")
    unrealizedPnlPct: float = Field(..., description="未实现盈亏百分比")


class OpenOrderResponseData(ApiResponseModel):
    orderRef: str = Field(..., description="订单引用号")
    symbol: str = Field(..., description="交易对")
    side: TradeSideEnum = Field(..., description="方向")
    botName: str = Field(..., description="所属 Bot")
    orderType: OrderTypeEnum = Field(..., description="订单类型")
    status: OrderStatusEnum = Field(..., description="订单状态")
    price: float = Field(..., description="委托价")
    quantity: float = Field(..., description="委托数量")
    filledPct: float = Field(..., description="成交进度百分比")
    createdAt: str = Field(..., description="挂单时间文案")


class TradeStatsResponseData(ApiResponseModel):
    totalTrades: int = Field(..., description="总交易数")
    winCount: int = Field(..., description="盈利笔数")
    lossCount: int = Field(..., description="亏损笔数")
    winRate: float = Field(..., description="胜率 %")
    profitFactor: float = Field(..., description="盈亏比")
    netPnl: float = Field(..., description="净盈亏")
    netPnlPct: float = Field(..., description="净盈亏百分比")
    window: str = Field(..., description="统计窗口文案")


class TradeExportResponseData(ApiResponseModel):
    filename: str = Field(..., description="建议下载文件名")
    contentType: str = Field(..., description="MIME 类型")
    csv: str = Field(..., description="CSV 文本内容")
