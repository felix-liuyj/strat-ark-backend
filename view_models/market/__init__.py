"""行情视图模型。

行情数据全部来自交易所行情 service（拟真），只读端点不强制登录；自选交易对读写
数据库且需登录。蜡烛图 / 订单簿 / 成交流以确定性 mock 保证前端联调可复现。
"""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.market import WatchlistAddForm
from libs.auth.permissions import PermissionChecker
from libs.integrations import market_data
from libs.integrations.market_data import MarketTicker
from models.market import MarketWatchlistItem
from responses.market import (
    CandleResponseData,
    MarketDetailResponseData,
    MarketOverviewResponseData,
    MarketTickerResponseData,
    OrderBookLevelResponseData,
    OrderBookResponseData,
    TickerAiSnapshotResponseData,
    TopMoversResponseData,
    TradeTickResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = (
    "AddWatchlistViewModel",
    "GetMarketDetailViewModel",
    "ListHeatmapViewModel",
    "ListTickersViewModel",
    "ListWatchlistViewModel",
    "MarketOverviewViewModel",
    "RemoveWatchlistViewModel",
    "TopMoversViewModel",
)


def _ticker_to_response(ticker: MarketTicker) -> MarketTickerResponseData:
    return MarketTickerResponseData(
        symbol=ticker.symbol,
        base=ticker.base,
        quote=ticker.quote,
        price=ticker.price,
        changePct=ticker.change_pct,
        volume=ticker.volume,
        signal=ticker.signal,
        signalTone=ticker.signal_tone,
        marketType=ticker.market_type,
    )


class MarketOverviewViewModel(BaseViewModel):
    """市场总览 KPI（总市值 / 成交额 / 占比 / 情绪）。只读，不强制登录。"""

    def __init__(self, request: Request) -> None:
        super().__init__(request=request)

    async def before(self) -> None:
        await super().before()
        overview = await market_data.get_market_overview()
        data = MarketOverviewResponseData(
            totalMarketCap=overview.total_market_cap,
            totalMarketCapChangePct=overview.total_market_cap_change_pct,
            volume24h=overview.volume_24h,
            volume24hChangePct=overview.volume_24h_change_pct,
            btcDominance=overview.btc_dominance,
            btcDominanceChangePct=overview.btc_dominance_change_pct,
            fearGreed=overview.fear_greed,
            fearGreedLabel=overview.fear_greed_label,
        )
        self.operating_successfully(data)


class ListTickersViewModel(BaseViewModel):
    """行情列表（自选行情底表，可按现货 / 合约过滤）。只读，不强制登录。"""

    def __init__(self, request: Request, market_type: str | None) -> None:
        super().__init__(request=request)
        self.market_type = market_type

    async def before(self) -> None:
        await super().before()
        tickers = await market_data.list_tickers()
        if self.market_type and self.market_type != "all":
            tickers = [t for t in tickers if t.market_type == self.market_type]
        self.operating_successfully([_ticker_to_response(t) for t in tickers])


class TopMoversViewModel(BaseViewModel):
    """涨跌榜（涨幅榜 + 跌幅榜）。只读，不强制登录。"""

    def __init__(self, request: Request, limit: int) -> None:
        super().__init__(request=request)
        self.limit = max(1, min(limit, 10))

    async def before(self) -> None:
        await super().before()
        gainers, losers = await market_data.get_top_movers(self.limit)
        data = TopMoversResponseData(
            gainers=[_ticker_to_response(t) for t in gainers],
            losers=[_ticker_to_response(t) for t in losers],
        )
        self.operating_successfully(data)


class ListHeatmapViewModel(BaseViewModel):
    """市场热力图（币种 + 24h 涨跌幅）。只读，不强制登录。"""

    def __init__(self, request: Request) -> None:
        super().__init__(request=request)

    async def before(self) -> None:
        await super().before()
        # 热力图为「币种 -> 涨跌幅」的轻量映射，直接返回字典列表。
        data = [{"symbol": sym, "changePct": pct} for sym, pct in await market_data.get_heatmap()]
        self.operating_successfully(data)


class GetMarketDetailViewModel(BaseViewModel):
    """单币种详情（行情 + K 线 + 订单簿 + 成交流 + AI 快照）。只读，不强制登录。"""

    def __init__(self, request: Request, symbol: str) -> None:
        super().__init__(request=request)
        self.symbol = symbol

    async def before(self) -> None:
        await super().before()
        detail = await market_data.get_ticker_detail(self.symbol)
        if detail is None:
            self.not_found("交易对不存在")
            return
        ticker, snapshot = detail
        candles = await market_data.build_candles(self.symbol)
        order_book = await market_data.get_order_book(self.symbol)
        tape = await market_data.get_trade_tape(self.symbol)

        data = MarketDetailResponseData(
            ticker=_ticker_to_response(ticker),
            candles=[
                CandleResponseData(ts=c.ts, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume)
                for c in candles
            ],
            orderBook=OrderBookResponseData(
                asks=[
                    OrderBookLevelResponseData(price=a.price, amount=a.amount, total=a.total) for a in order_book.asks
                ],
                bids=[
                    OrderBookLevelResponseData(price=b.price, amount=b.amount, total=b.total) for b in order_book.bids
                ],
                midPrice=order_book.mid_price,
                bidRatio=order_book.bid_ratio,
            ),
            tape=[TradeTickResponseData(price=t.price, amount=t.amount, ts=t.ts, isBuy=t.is_buy) for t in tape],
            aiSnapshot=TickerAiSnapshotResponseData(
                rating=snapshot.rating,
                confidence=snapshot.confidence,
                trend=snapshot.trend,
                entryLow=snapshot.entry_low,
                entryHigh=snapshot.entry_high,
                stopLoss=snapshot.stop_loss,
                takeProfit=snapshot.take_profit,
                generatedAt=snapshot.generated_at,
            ),
        )
        self.operating_successfully(data)


class ListWatchlistViewModel(BaseViewModel):
    """用户自选行情（DB 自选 + service 实时行情）。需登录。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        items = (
            await self.db.scalars(
                select(MarketWatchlistItem)
                .where(MarketWatchlistItem.user_id == int(self.checker.user_id))
                .order_by(MarketWatchlistItem.id.asc())
            )
        ).all()
        result: list[MarketTickerResponseData] = []
        for item in items:
            ticker = await market_data.get_ticker(item.symbol)
            if ticker is not None:
                result.append(_ticker_to_response(ticker))
        self.operating_successfully(result)


class AddWatchlistViewModel(BaseViewModel):
    """新增自选交易对（已存在则视为无变更）。需登录。"""

    def __init__(self, request: Request, db: AsyncSession, form: WatchlistAddForm, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        symbol = self.form.symbol.strip().upper()
        if await market_data.get_ticker(symbol) is None:
            self.illegal_parameters("交易对不存在")
            return

        user_id = int(self.checker.user_id)
        existing = await self.db.scalar(
            select(MarketWatchlistItem).where(
                MarketWatchlistItem.user_id == user_id, MarketWatchlistItem.symbol == symbol
            )
        )
        if existing is not None:
            self.nothing_changed()
            return

        item = MarketWatchlistItem(user_id=user_id, symbol=symbol, market_type=self.form.marketType)
        self.db.add(item)
        await self.db.commit()
        self.operating_successfully()


class RemoveWatchlistViewModel(BaseViewModel):
    """移除自选交易对。需登录。"""

    def __init__(self, request: Request, db: AsyncSession, symbol: str, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.symbol = symbol
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        normalized = self.symbol.strip().upper()
        item = await self.db.scalar(
            select(MarketWatchlistItem).where(
                MarketWatchlistItem.user_id == int(self.checker.user_id),
                MarketWatchlistItem.symbol == normalized,
            )
        )
        if item is None:
            self.not_found("自选交易对不存在")
            return
        await self.db.delete(item)
        await self.db.commit()
        self.operating_successfully()
