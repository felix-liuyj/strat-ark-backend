"""交易所行情数据集成。

默认对接公共行情 REST（Binance 现货 ticker / K 线 / 订单簿 / 成交流，无需密钥；
市场总览取 CoinGecko global + alternative.me 恐惧贪婪指数）。所有外呼经 httpx 异步；
任一请求失败时返回空集合或不可用字段，不再回退演示行情。
REST base 可经 ``MARKET_DATA_REST_URL`` 覆盖（指向自建代理 / 镜像）。ViewModel 只调用
这里的 async 函数，不接触交易所协议细节。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from configs import get_settings
from libs.logger import logger

__all__ = (
    "VALID_CANDLE_INTERVALS",
    "Candle",
    "MarketOverview",
    "MarketTicker",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "TickerAiSnapshot",
    "TradeTick",
    "build_candles",
    "build_spark",
    "get_heatmap",
    "get_market_overview",
    "get_order_book",
    "get_ticker",
    "get_ticker_detail",
    "get_top_movers",
    "get_trade_tape",
    "list_tickers",
)

# K 线周期白名单（与 Binance klines interval 对齐，前端周期切换器同源）。
VALID_CANDLE_INTERVALS: tuple[str, ...] = ("1m", "15m", "1h", "4h", "1d")

# 各周期对应的时间步长（K 线时间轴校验与处理用）。
_INTERVAL_STEP: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}

# 7D 走势 sparkline 的取样点数（日线收盘价）。
_SPARK_POINTS = 8

# 公共行情源默认地址（可被 settings 覆盖 REST base）。
_DEFAULT_REST = "https://api.binance.com"
_COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"
_FNG_URL = "https://api.alternative.me/fng/?limit=1"
_HTTP_TIMEOUT = 8.0

# 平台展示的交易对宇宙（与前端自选一致）。
_UNIVERSE: list[tuple[str, str, str]] = [
    ("BTC/USDT", "BTC", "USDT"),
    ("ETH/USDT", "ETH", "USDT"),
    ("SOL/USDT", "SOL", "USDT"),
    ("BNB/USDT", "BNB", "USDT"),
    ("XRP/USDT", "XRP", "USDT"),
    ("AVAX/USDT", "AVAX", "USDT"),
    ("DOGE/USDT", "DOGE", "USDT"),
    ("LINK/USDT", "LINK", "USDT"),
]


# ============================ DTO ============================


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
        spark: list[float] | None = None,
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
        # 7D 日线收盘走势（仅列表/自选场景按需填充，避免无谓外呼）。
        self.spark: list[float] = spark or []


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
    """单交易对 AI 快照（详情页右侧卡，技术位由真实价格 + 近端波动派生）。"""

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


# ============================ 工具 ============================


def _rest_base() -> str:
    return (getattr(get_settings(), "MARKET_DATA_REST_URL", None) or _DEFAULT_REST).rstrip("/")


def _exchange_symbol(symbol: str) -> str:
    """``BTC/USDT`` -> ``BTCUSDT``。"""
    return symbol.replace("/", "").replace("-", "").upper()


def _split_symbol(symbol: str) -> tuple[str, str]:
    if "/" in symbol:
        base, quote = symbol.split("/", 1)
        return base.upper(), quote.upper()
    return symbol.upper(), "USDT"


def _signal_for(change_pct: float) -> tuple[str, str]:
    """由 24h 涨跌幅派生展示信号标签 + 配色（轻量启发式，非投研结论）。"""
    if change_pct >= 5:
        return "Long", "run"
    if change_pct >= 1:
        return "Watch", "warn"
    if change_pct <= -5:
        return "Avoid", "live"
    return "Neutral", "neutral"


def _fmt_usd_compact(value: float) -> str:
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(value) >= size:
            return f"${value / size:.2f}{unit}"
    return f"${value:,.0f}"


async def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


# ============================ 真实实现 ============================


def _ticker_from_binance(symbol: str, base: str, quote: str, row: dict[str, Any]) -> MarketTicker:
    price = float(row.get("lastPrice", 0) or 0)
    pct = float(row.get("priceChangePercent", 0) or 0)
    vol = float(row.get("quoteVolume", 0) or 0)
    signal, tone = _signal_for(pct)
    return MarketTicker(symbol, base, quote, price, pct, vol, signal, tone, "spot")


async def _attach_sparks(tickers: list[MarketTicker]) -> None:
    """并发为一组 ticker 填充 7D 走势。"""
    sparks = await asyncio.gather(*(build_spark(t.symbol) for t in tickers))
    for ticker, spark in zip(tickers, sparks, strict=True):
        ticker.spark = spark


async def list_tickers(with_spark: bool = False) -> list[MarketTicker]:
    """自选行情全表（Binance 24h ticker）。``with_spark`` 时附带 7D 走势。"""
    symbols = [_exchange_symbol(sym) for sym, _, _ in _UNIVERSE]
    try:
        import json

        rows = await _get_json(f"{_rest_base()}/api/v3/ticker/24hr", {"symbols": json.dumps(symbols)})
        by_symbol = {str(r.get("symbol")): r for r in rows} if isinstance(rows, list) else {}
        tickers = [
            _ticker_from_binance(sym, base, quote, row)
            for sym, base, quote in _UNIVERSE
            if (row := by_symbol.get(_exchange_symbol(sym))) is not None
        ]
    except Exception as exc:
        logger.warning(f"market_data.list_tickers failed: {exc}")
        tickers = []
    if with_spark:
        await _attach_sparks(tickers)
    return tickers


async def get_ticker(symbol: str, with_spark: bool = False) -> MarketTicker | None:
    """按交易对返回单条行情（Binance）。``with_spark`` 时附带 7D 走势。"""
    base, quote = _split_symbol(symbol)
    canonical = f"{base}/{quote}"
    try:
        row = await _get_json(f"{_rest_base()}/api/v3/ticker/24hr", {"symbol": _exchange_symbol(symbol)})
        if isinstance(row, dict) and row.get("lastPrice") is not None:
            ticker = _ticker_from_binance(canonical, base, quote, row)
        else:
            ticker = None
    except Exception as exc:
        logger.warning(f"market_data.get_ticker failed: {exc}")
        ticker = None
    if ticker is not None and with_spark:
        ticker.spark = await build_spark(canonical)
    return ticker


def _normalize_interval(interval: str) -> str:
    return interval if interval in _INTERVAL_STEP else "1h"


async def build_candles(symbol: str, count: int = 44, interval: str = "1h") -> list[Candle]:
    """K 线序列（Binance klines，周期见 ``VALID_CANDLE_INTERVALS``）。"""
    interval = _normalize_interval(interval)
    try:
        rows = await _get_json(
            f"{_rest_base()}/api/v3/klines",
            {"symbol": _exchange_symbol(symbol), "interval": interval, "limit": count},
        )
        if not isinstance(rows, list) or not rows:
            return []
        return [
            Candle(
                ts=int(k[0] // 1000),
                open_=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
            )
            for k in rows
        ]
    except Exception as exc:
        logger.warning(f"market_data.build_candles failed: {exc}")
        return []


async def build_spark(symbol: str, points: int = _SPARK_POINTS) -> list[float]:
    """7D 走势序列（Binance 日线收盘价）。"""
    try:
        rows = await _get_json(
            f"{_rest_base()}/api/v3/klines",
            {"symbol": _exchange_symbol(symbol), "interval": "1d", "limit": points},
        )
        if not isinstance(rows, list) or not rows:
            return []
        return [round(float(k[4]), 4) for k in rows]
    except Exception as exc:
        logger.warning(f"market_data.build_spark failed: {exc}")
        return []


async def get_order_book(symbol: str, depth: int = 9) -> OrderBookSnapshot:
    """订单簿快照（Binance depth）。"""
    try:
        data = await _get_json(
            f"{_rest_base()}/api/v3/depth", {"symbol": _exchange_symbol(symbol), "limit": max(depth, 5)}
        )
        raw_asks = data.get("asks", [])[:depth]
        raw_bids = data.get("bids", [])[:depth]
        if not raw_asks or not raw_bids:
            return OrderBookSnapshot(asks=[], bids=[], mid_price=0, bid_ratio=0)

        def _levels(rows: list[list[str]]) -> list[OrderBookLevel]:
            cumulative = 0.0
            out: list[OrderBookLevel] = []
            for price, amount in rows:
                amt = float(amount)
                cumulative += amt
                out.append(OrderBookLevel(price=float(price), amount=amt, total=round(cumulative, 4)))
            return out

        asks = list(reversed(_levels(raw_asks)))
        bids = _levels(raw_bids)
        best_ask = float(raw_asks[0][0])
        best_bid = float(raw_bids[0][0])
        mid = round((best_ask + best_bid) / 2, 4)
        bid_vol = sum(float(b[1]) for b in raw_bids)
        ask_vol = sum(float(a[1]) for a in raw_asks)
        bid_ratio = round(bid_vol / (bid_vol + ask_vol), 2) if (bid_vol + ask_vol) else 0.5
        return OrderBookSnapshot(asks=asks, bids=bids, mid_price=mid, bid_ratio=bid_ratio)
    except Exception as exc:
        logger.warning(f"market_data.get_order_book failed: {exc}")
        return OrderBookSnapshot(asks=[], bids=[], mid_price=0, bid_ratio=0)


async def get_trade_tape(symbol: str, count: int = 12) -> list[TradeTick]:
    """成交流（Binance recent trades）。"""
    try:
        rows = await _get_json(
            f"{_rest_base()}/api/v3/trades", {"symbol": _exchange_symbol(symbol), "limit": count}
        )
        if not isinstance(rows, list) or not rows:
            return []
        # isBuyerMaker=True 表示卖方主动成交，主动买入为其取反。
        return [
            TradeTick(
                price=float(r["price"]),
                amount=round(float(r["qty"]), 3),
                ts=int(int(r["time"]) // 1000),
                is_buy=not bool(r.get("isBuyerMaker")),
            )
            for r in rows
        ]
    except Exception as exc:
        logger.warning(f"market_data.get_trade_tape failed: {exc}")
        return []


async def get_top_movers(limit: int = 3) -> tuple[list[MarketTicker], list[MarketTicker]]:
    """涨幅榜与跌幅榜（基于真实 list_tickers）。"""
    tickers = await list_tickers()
    gainers = sorted([t for t in tickers if t.change_pct >= 0], key=lambda t: t.change_pct, reverse=True)
    losers = sorted([t for t in tickers if t.change_pct < 0], key=lambda t: t.change_pct)
    return gainers[:limit], losers[:limit]


async def get_heatmap() -> list[tuple[str, float]]:
    """热力图（真实 24h 涨跌幅）。"""
    tickers = await list_tickers()
    return [(t.base, round(t.change_pct, 1)) for t in tickers]


def _fng_label(classification: str) -> str:
    mapping = {
        "extreme fear": "market.extremeFear",
        "fear": "market.fear",
        "neutral": "market.neutral",
        "greed": "market.greed",
        "extreme greed": "market.extremeGreed",
    }
    return mapping.get(classification.strip().lower(), "market.neutral")


async def get_market_overview() -> MarketOverview:
    """市场总览（CoinGecko global + alternative.me 情绪）。"""
    try:
        gl = (await _get_json(_COINGECKO_GLOBAL)).get("data", {})
        total_cap = float(gl["total_market_cap"]["usd"])
        total_vol = float(gl["total_volume"]["usd"])
        btc_dom = float(gl["market_cap_percentage"]["btc"])
        cap_change = float(gl.get("market_cap_change_percentage_24h_usd", 0) or 0)
        total_market_cap = _fmt_usd_compact(total_cap)
        volume_24h = _fmt_usd_compact(total_vol)
        total_market_cap_change_pct = round(cap_change, 2)
        btc_dominance = round(btc_dom, 1)
    except Exception as exc:
        logger.warning(f"market_data.get_market_overview global failed: {exc}")
        total_market_cap = ""
        volume_24h = ""
        total_market_cap_change_pct = 0.0
        btc_dominance = 0.0

    fear_greed = 0
    fear_greed_label = ""
    try:
        fng = (await _get_json(_FNG_URL))["data"][0]
        fear_greed = int(fng["value"])
        fear_greed_label = _fng_label(str(fng.get("value_classification", "")))
    except Exception as exc:
        logger.warning(f"market_data.get_market_overview fng failed: {exc}")

    return MarketOverview(
        total_market_cap=total_market_cap,
        total_market_cap_change_pct=total_market_cap_change_pct,
        volume_24h=volume_24h,
        volume_24h_change_pct=0.0,
        btc_dominance=btc_dominance,
        btc_dominance_change_pct=0.0,
        fear_greed=fear_greed,
        fear_greed_label=fear_greed_label,
    )


async def get_ticker_detail(symbol: str) -> tuple[MarketTicker, TickerAiSnapshot] | None:
    """单交易对详情（真实行情 + 由真实价格/近端 K 线派生的技术快照）。"""
    ticker = await get_ticker(symbol)
    if ticker is None:
        return None
    candles = await build_candles(symbol, count=24)
    if candles:
        highs = max(c.high for c in candles)
        lows = min(c.low for c in candles)
        trend_up = candles[-1].close >= candles[0].close
    else:
        highs, lows, trend_up = ticker.price * 1.05, ticker.price * 0.95, ticker.change_pct >= 0
    snapshot = TickerAiSnapshot(
        rating="Long" if trend_up else "Watch",
        confidence=68 if trend_up else 55,
        trend="Trend Up" if trend_up else "Range",
        entry_low=round(lows + (ticker.price - lows) * 0.3, 4),
        entry_high=round(ticker.price * 1.003, 4),
        stop_loss=round(lows * 0.997, 4),
        take_profit=[round(highs, 4), round(highs * 1.02, 4)],
        # ISO 时间戳，由前端按本地时区格式化展示。
        generated_at=datetime.now(UTC).isoformat(),
    )
    return ticker, snapshot
