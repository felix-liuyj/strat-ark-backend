"""行情响应数据模型。

覆盖市场总览、自选行情、涨跌榜、热力图、K 线、订单簿、成交流与单币种详情，
与前端 MarketPage / MarketDetailPage 数据形状对齐。
"""

from pydantic import Field

from libs.schema import ApiResponseModel

__all__ = (
    "CandleResponseData",
    "HeatmapCellResponseData",
    "MarketDetailResponseData",
    "MarketOverviewResponseData",
    "MarketTickerResponseData",
    "OrderBookLevelResponseData",
    "OrderBookResponseData",
    "TickerAiSnapshotResponseData",
    "TopMoversResponseData",
    "TradeTickResponseData",
)


class MarketTickerResponseData(ApiResponseModel):
    symbol: str = Field(..., description="交易对")
    base: str = Field(..., description="基础币")
    quote: str = Field(..., description="计价币")
    price: float = Field(..., description="最新价")
    changePct: float = Field(..., description="24h 涨跌幅 %")
    volume: float = Field(..., description="24h 成交额")
    signal: str = Field(..., description="AI 信号标签")
    signalTone: str = Field(..., description="信号配色：run / warn / neutral / live")
    marketType: str = Field(..., description="现货 spot / 合约 futures")
    spark: list[float] = Field(default_factory=list, description="7D 日线收盘走势（行情列表/自选填充，其余场景为空）")


class MarketOverviewResponseData(ApiResponseModel):
    totalMarketCap: str = Field(..., description="总市值")
    totalMarketCapChangePct: float = Field(..., description="总市值 24h 变化 %")
    volume24h: str = Field(..., description="24h 成交额")
    volume24hChangePct: float = Field(..., description="24h 成交额变化 %")
    btcDominance: float = Field(..., description="BTC 占比 %")
    btcDominanceChangePct: float = Field(..., description="BTC 占比变化 %")
    fearGreed: int = Field(..., description="恐惧贪婪指数")
    fearGreedLabel: str = Field(..., description="情绪 i18n key")


class TopMoversResponseData(ApiResponseModel):
    gainers: list[MarketTickerResponseData] = Field(..., description="涨幅榜")
    losers: list[MarketTickerResponseData] = Field(..., description="跌幅榜")


class HeatmapCellResponseData(ApiResponseModel):
    symbol: str = Field(..., description="基础币符号")
    changePct: float = Field(..., description="24h 涨跌幅 %")


class CandleResponseData(ApiResponseModel):
    ts: int = Field(..., description="时间戳（秒）")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: float = Field(..., description="成交量")


class OrderBookLevelResponseData(ApiResponseModel):
    price: float = Field(..., description="价格")
    amount: float = Field(..., description="数量")
    total: float = Field(..., description="累计数量")


class OrderBookResponseData(ApiResponseModel):
    asks: list[OrderBookLevelResponseData] = Field(..., description="卖盘（已逆序）")
    bids: list[OrderBookLevelResponseData] = Field(..., description="买盘")
    midPrice: float = Field(..., description="中间价")
    bidRatio: float = Field(..., description="买盘占比 0-1")


class TradeTickResponseData(ApiResponseModel):
    price: float = Field(..., description="成交价")
    amount: float = Field(..., description="成交量")
    ts: int = Field(..., description="时间戳（秒）")
    isBuy: bool = Field(..., description="是否主动买入")


class TickerAiSnapshotResponseData(ApiResponseModel):
    rating: str = Field(..., description="评级，如 Watch / Long")
    confidence: int = Field(..., description="置信度 %")
    trend: str = Field(..., description="趋势文案")
    entryLow: float = Field(..., description="入场区间下界")
    entryHigh: float = Field(..., description="入场区间上界")
    stopLoss: float = Field(..., description="止损价")
    takeProfit: list[float] = Field(..., description="止盈价列表")
    generatedAt: str = Field(..., description="生成时间文案")


class MarketDetailResponseData(ApiResponseModel):
    ticker: MarketTickerResponseData = Field(..., description="标的行情")
    candles: list[CandleResponseData] = Field(..., description="K 线序列")
    orderBook: OrderBookResponseData = Field(..., description="订单簿快照")
    tape: list[TradeTickResponseData] = Field(..., description="成交流")
    aiSnapshot: TickerAiSnapshotResponseData = Field(..., description="AI 快照")
