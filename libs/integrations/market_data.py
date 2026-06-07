"""交易所行情数据 service stub（REST 行情 / WebSocket 快照的占位实现）。

真实实现会对接交易所聚合行情（Binance / OKX 等）的 ticker、K 线、订单簿、成交流。
当前阶段返回**确定性拟真 mock**：同一交易对每次调用结果稳定（用交易对哈希播种），
保证前端联调时数据可复现。ViewModel 只调用这里的函数，不直接接触交易所协议细节。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

__all__ = (
    "Candle",
    "MarketOverview",
    "MarketTicker",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "TickerAiSnapshot",
    "TradeTick",
    "build_candles",
    "get_heatmap",
    "get_market_overview",
    "get_order_book",
    "get_ticker",
    "get_ticker_detail",
    "get_top_movers",
    "get_trade_tape",
    "list_tickers",
)


# -- 拟真数据结构（service 内部 DTO，与响应层 ApiResponseModel 解耦） --


class MarketTicker:
    """单交易对行情快照。"""

    def __init__(
        self,
        symbol: str,
        base: str,
        quote: str,
        price: float,
        change_pct: float,
        volume: float,
        signal: str,
        signal_tone: str,
        market_type: str,
    ) -> None:
        self.symbol = symbol
        self.base = base
        self.quote = quote
        self.price = price
        self.change_pct = change_pct
        self.volume = volume
        self.signal = signal
        self.signal_tone = signal_tone
        self.market_type = market_type


class Candle:
    """单根 K 线（开高低收 + 时间戳）。"""

    def __init__(self, ts: int, open_: float, high: float, low: float, close: float, volume: float) -> None:
        self.ts = ts
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


class OrderBookLevel:
    """订单簿单档（价 / 量 / 累计量）。"""

    def __init__(self, price: float, amount: float, total: float) -> None:
        self.price = price
        self.amount = amount
        self.total = total


class OrderBookSnapshot:
    """订单簿快照（卖盘 + 买盘 + 中间价 + 买盘占比）。"""

    def __init__(
        self,
        asks: list[OrderBookLevel],
        bids: list[OrderBookLevel],
        mid_price: float,
        bid_ratio: float,
    ) -> None:
        self.asks = asks
        self.bids = bids
        self.mid_price = mid_price
        self.bid_ratio = bid_ratio


class TradeTick:
    """成交流单笔（价 / 量 / 时间 / 主动买卖方向）。"""

    def __init__(self, price: float, amount: float, ts: int, is_buy: bool) -> None:
        self.price = price
        self.amount = amount
        self.ts = ts
        self.is_buy = is_buy


class TickerAiSnapshot:
    """单交易对 AI 快照（详情页右侧卡）。"""

    def __init__(
        self,
        rating: str,
        confidence: int,
        trend: str,
        entry_low: float,
        entry_high: float,
        stop_loss: float,
        take_profit: list[float],
        generated_at: str,
    ) -> None:
        self.rating = rating
        self.confidence = confidence
        self.trend = trend
        self.entry_low = entry_low
        self.entry_high = entry_high
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.generated_at = generated_at


class MarketOverview:
    """市场总览 KPI（总市值 / 成交额 / 占比 / 情绪）。"""

    def __init__(
        self,
        total_market_cap: str,
        total_market_cap_change_pct: float,
        volume_24h: str,
        volume_24h_change_pct: float,
        btc_dominance: float,
        btc_dominance_change_pct: float,
        fear_greed: int,
        fear_greed_label: str,
    ) -> None:
        self.total_market_cap = total_market_cap
        self.total_market_cap_change_pct = total_market_cap_change_pct
        self.volume_24h = volume_24h
        self.volume_24h_change_pct = volume_24h_change_pct
        self.btc_dominance = btc_dominance
        self.btc_dominance_change_pct = btc_dominance_change_pct
        self.fear_greed = fear_greed
        self.fear_greed_label = fear_greed_label


# -- 确定性 RNG（线性同余，复刻前端 data.ts 的播种逻辑，保证可复现） --


class _Rng:
    """线性同余随机数发生器，与前端蜡烛图生成算法一致。"""

    def __init__(self, seed: int) -> None:
        self._seed = seed

    def next(self) -> float:
        self._seed = (self._seed * 9301 + 49297) % 233280
        return self._seed / 233280


def _seed_of(symbol: str) -> int:
    """由交易对名派生稳定种子，使每个交易对的拟真数据可复现。"""
    return sum(ord(ch) for ch in symbol) % 9973 + 7


# -- 静态自选行情底表（与前端 WATCHLIST 对齐） --

_WATCHLIST: list[dict[str, object]] = [
    {
        "symbol": "BTC/USDT",
        "base": "BTC",
        "quote": "USDT",
        "price": 68610.0,
        "pct": 1.42,
        "vol": 32.4e9,
        "signal": "Watch",
        "tone": "warn",
    },
    {
        "symbol": "ETH/USDT",
        "base": "ETH",
        "quote": "USDT",
        "price": 3512.0,
        "pct": 1.86,
        "vol": 14.1e9,
        "signal": "Long",
        "tone": "run",
    },
    {
        "symbol": "SOL/USDT",
        "base": "SOL",
        "quote": "USDT",
        "price": 172.40,
        "pct": 8.61,
        "vol": 6.8e9,
        "signal": "Long",
        "tone": "run",
    },
    {
        "symbol": "BNB/USDT",
        "base": "BNB",
        "quote": "USDT",
        "price": 604.2,
        "pct": -0.42,
        "vol": 1.9e9,
        "signal": "Neutral",
        "tone": "neutral",
    },
    {
        "symbol": "XRP/USDT",
        "base": "XRP",
        "quote": "USDT",
        "price": 0.5240,
        "pct": 2.11,
        "vol": 2.2e9,
        "signal": "Watch",
        "tone": "warn",
    },
    {
        "symbol": "AVAX/USDT",
        "base": "AVAX",
        "quote": "USDT",
        "price": 38.20,
        "pct": 6.1,
        "vol": 0.9e9,
        "signal": "Long",
        "tone": "run",
    },
    {
        "symbol": "DOGE/USDT",
        "base": "DOGE",
        "quote": "USDT",
        "price": 0.1420,
        "pct": -5.3,
        "vol": 1.1e9,
        "signal": "Avoid",
        "tone": "live",
    },
    {
        "symbol": "LINK/USDT",
        "base": "LINK",
        "quote": "USDT",
        "price": 18.90,
        "pct": 4.7,
        "vol": 0.6e9,
        "signal": "Long",
        "tone": "run",
    },
]

# 热力图底表（与前端 HEAT_DATA 对齐）。
_HEATMAP: list[tuple[str, float]] = [
    ("BTC", 1.4),
    ("ETH", 1.9),
    ("SOL", 8.6),
    ("BNB", -0.4),
    ("XRP", 2.1),
    ("AVAX", 6.1),
    ("DOGE", -5.3),
    ("LINK", 4.7),
    ("ADA", -3.8),
    ("DOT", 0.9),
    ("MATIC", -1.2),
    ("ATOM", 3.3),
]


def _to_ticker(row: dict[str, object]) -> MarketTicker:
    return MarketTicker(
        symbol=str(row["symbol"]),
        base=str(row["base"]),
        quote=str(row["quote"]),
        price=float(row["price"]),  # type: ignore[arg-type]
        change_pct=float(row["pct"]),  # type: ignore[arg-type]
        volume=float(row["vol"]),  # type: ignore[arg-type]
        signal=str(row["signal"]),
        signal_tone=str(row["tone"]),
        market_type="spot",
    )


def list_tickers() -> list[MarketTicker]:
    """返回自选行情全表。"""
    return [_to_ticker(row) for row in _WATCHLIST]


def get_ticker(symbol: str) -> MarketTicker | None:
    """按交易对返回单条行情，不存在返回 None。"""
    target = symbol.strip().upper()
    for row in _WATCHLIST:
        if str(row["symbol"]).upper() == target:
            return _to_ticker(row)
    return None


def build_candles(symbol: str, count: int = 44) -> list[Candle]:
    """生成确定性 K 线序列（与前端蜡烛图算法一致，按交易对播种）。"""
    rng = _Rng(_seed_of(symbol))
    base_price = get_ticker(symbol)
    price = base_price.price if base_price else 132.0
    now = datetime.now(UTC)
    candles: list[Candle] = []
    for i in range(count):
        open_ = price
        close = open_ + (rng.next() - 0.42) * (price * 0.012)
        high = max(open_, close) + rng.next() * (price * 0.006)
        low = min(open_, close) - rng.next() * (price * 0.006)
        volume = rng.next() * 1800 + 200
        ts = int((now - timedelta(hours=count - i)).timestamp())
        candles.append(Candle(ts=ts, open_=open_, high=high, low=low, close=close, volume=volume))
        price = close
    return candles


def get_order_book(symbol: str, depth: int = 9) -> OrderBookSnapshot:
    """生成确定性订单簿快照（卖盘 + 买盘 + 中间价）。"""
    rng = _Rng(_seed_of(symbol) + 3)
    ticker = get_ticker(symbol)
    mid = ticker.price if ticker else 68610.0

    def _side(is_ask: bool) -> list[OrderBookLevel]:
        price = mid
        cumulative = 0.0
        levels: list[OrderBookLevel] = []
        for _ in range(depth):
            price += (1 if is_ask else -1) * (4 + round(rng.next() * 8))
            amount = rng.next() * 1.8 + 0.05
            cumulative += amount
            levels.append(OrderBookLevel(price=price, amount=amount, total=cumulative))
        return list(reversed(levels)) if is_ask else levels

    return OrderBookSnapshot(asks=_side(True), bids=_side(False), mid_price=mid, bid_ratio=0.53)


def get_trade_tape(symbol: str, count: int = 12) -> list[TradeTick]:
    """生成确定性成交流（最近成交）。"""
    rng = _Rng(_seed_of(symbol) + 5)
    ticker = get_ticker(symbol)
    price = ticker.price if ticker else 68610.0
    now = datetime.now(UTC)
    ticks: list[TradeTick] = []
    for i in range(count):
        is_buy = rng.next() > 0.45
        price += (1 if is_buy else -1) * round(rng.next() * 6)
        amount = round(rng.next() * 0.6 + 0.002, 3)
        ts = int((now - timedelta(seconds=count - i)).timestamp())
        ticks.append(TradeTick(price=price, amount=amount, ts=ts, is_buy=is_buy))
    return ticks


def get_top_movers(limit: int = 3) -> tuple[list[MarketTicker], list[MarketTicker]]:
    """返回涨幅榜与跌幅榜（各 limit 条）。"""
    tickers = list_tickers()
    gainers = sorted([t for t in tickers if t.change_pct >= 0], key=lambda t: t.change_pct, reverse=True)
    losers = sorted([t for t in tickers if t.change_pct < 0], key=lambda t: t.change_pct)
    return gainers[:limit], losers[:limit]


def get_heatmap() -> list[tuple[str, float]]:
    """返回热力图数据（币种 + 24h 涨跌幅）。"""
    return list(_HEATMAP)


def get_market_overview() -> MarketOverview:
    """返回市场总览 KPI（拟真静态值）。"""
    return MarketOverview(
        total_market_cap="$2.38T",
        total_market_cap_change_pct=1.8,
        volume_24h="$98.2B",
        volume_24h_change_pct=-4.1,
        btc_dominance=54.2,
        btc_dominance_change_pct=0.3,
        fear_greed=62,
        fear_greed_label="Greed 贪婪",
    )


def get_ticker_detail(symbol: str) -> tuple[MarketTicker, TickerAiSnapshot] | None:
    """返回单交易对详情（行情 + AI 快照），不存在返回 None。"""
    ticker = get_ticker(symbol)
    if ticker is None:
        return None
    snapshot = TickerAiSnapshot(
        rating="Watch",
        confidence=72,
        trend="Trend Up",
        entry_low=ticker.price * 0.992,
        entry_high=ticker.price * 1.003,
        stop_loss=ticker.price * 0.969,
        take_profit=[ticker.price * 1.028, ticker.price * 1.05],
        generated_at=datetime.now(UTC).strftime("%H:%M"),
    )
    return ticker, snapshot
