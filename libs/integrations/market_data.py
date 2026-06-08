"""交易所行情数据集成。

默认对接公共行情 REST（Binance 现货 ticker / K 线 / 订单簿 / 成交流，无需密钥；
市场总览取 CoinGecko global + alternative.me 恐惧贪婪指数）。所有外呼经 httpx 异步，
任一请求失败（离线 / 限流 / 区域封锁）即回退到确定性拟真数据，保证联调与离线可用。
REST base 可经 ``MARKET_DATA_REST_URL`` 覆盖（指向自建代理 / 镜像）。ViewModel 只调用
这里的 async 函数，不接触交易所协议细节。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from configs import get_settings
from libs.logger import logger

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


# ============================ 确定性回退数据 ============================


class _Rng:
    """线性同余随机数发生器，与前端蜡烛图生成算法一致。"""

    def __init__(self, seed: int) -> None:
        self._seed = seed

    def next(self) -> float:
        self._seed = (self._seed * 9301 + 49297) % 233280
        return self._seed / 233280


def _seed_of(symbol: str) -> int:
    return sum(ord(ch) for ch in symbol) % 9973 + 7


_FALLBACK_ROWS: dict[str, tuple[float, float, float]] = {
    "BTC/USDT": (68610.0, 1.42, 32.4e9),
    "ETH/USDT": (3512.0, 1.86, 14.1e9),
    "SOL/USDT": (172.40, 8.61, 6.8e9),
    "BNB/USDT": (604.2, -0.42, 1.9e9),
    "XRP/USDT": (0.5240, 2.11, 2.2e9),
    "AVAX/USDT": (38.20, 6.1, 0.9e9),
    "DOGE/USDT": (0.1420, -5.3, 1.1e9),
    "LINK/USDT": (18.90, 4.7, 0.6e9),
}


def _demo_ticker(symbol: str) -> MarketTicker | None:
    row = _FALLBACK_ROWS.get(symbol.upper())
    if row is None:
        return None
    price, pct, vol = row
    base, quote = _split_symbol(symbol)
    signal, tone = _signal_for(pct)
    return MarketTicker(symbol.upper(), base, quote, price, pct, vol, signal, tone, "spot")


def _demo_tickers() -> list[MarketTicker]:
    return [t for sym, _, _ in _UNIVERSE if (t := _demo_ticker(sym)) is not None]


def _demo_candles(symbol: str, count: int) -> list[Candle]:
    rng = _Rng(_seed_of(symbol))
    ref = _demo_ticker(symbol)
    price = ref.price if ref else 132.0
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


def _demo_order_book(symbol: str, depth: int) -> OrderBookSnapshot:
    rng = _Rng(_seed_of(symbol) + 3)
    ref = _demo_ticker(symbol)
    mid = ref.price if ref else 68610.0

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


def _demo_trade_tape(symbol: str, count: int) -> list[TradeTick]:
    rng = _Rng(_seed_of(symbol) + 5)
    ref = _demo_ticker(symbol)
    price = ref.price if ref else 68610.0
    now = datetime.now(UTC)
    ticks: list[TradeTick] = []
    for i in range(count):
        is_buy = rng.next() > 0.45
        price += (1 if is_buy else -1) * round(rng.next() * 6)
        amount = round(rng.next() * 0.6 + 0.002, 3)
        ts = int((now - timedelta(seconds=count - i)).timestamp())
        ticks.append(TradeTick(price=price, amount=amount, ts=ts, is_buy=is_buy))
    return ticks


def _demo_overview() -> MarketOverview:
    return MarketOverview(
        total_market_cap="$2.38T",
        total_market_cap_change_pct=1.8,
        volume_24h="$98.2B",
        volume_24h_change_pct=-4.1,
        btc_dominance=54.2,
        btc_dominance_change_pct=0.3,
        fear_greed=62,
        fear_greed_label="market.greed",
    )


# ============================ 真实实现（失败回退 demo） ============================


def _ticker_from_binance(symbol: str, base: str, quote: str, row: dict[str, Any]) -> MarketTicker:
    price = float(row.get("lastPrice", 0) or 0)
    pct = float(row.get("priceChangePercent", 0) or 0)
    vol = float(row.get("quoteVolume", 0) or 0)
    signal, tone = _signal_for(pct)
    return MarketTicker(symbol, base, quote, price, pct, vol, signal, tone, "spot")


async def list_tickers() -> list[MarketTicker]:
    """自选行情全表（Binance 24h ticker，失败回退 demo）。"""
    symbols = [_exchange_symbol(sym) for sym, _, _ in _UNIVERSE]
    try:
        import json

        rows = await _get_json(f"{_rest_base()}/api/v3/ticker/24hr", {"symbols": json.dumps(symbols)})
        by_symbol = {str(r.get("symbol")): r for r in rows} if isinstance(rows, list) else {}
        out: list[MarketTicker] = []
        for sym, base, quote in _UNIVERSE:
            row = by_symbol.get(_exchange_symbol(sym))
            out.append(_ticker_from_binance(sym, base, quote, row) if row else _demo_ticker(sym))
        return [t for t in out if t is not None]
    except Exception as exc:
        logger.warning(f"market_data.list_tickers fallback to demo: {exc}")
        return _demo_tickers()


async def get_ticker(symbol: str) -> MarketTicker | None:
    """按交易对返回单条行情（Binance，失败回退 demo）。"""
    base, quote = _split_symbol(symbol)
    canonical = f"{base}/{quote}"
    try:
        row = await _get_json(f"{_rest_base()}/api/v3/ticker/24hr", {"symbol": _exchange_symbol(symbol)})
        if isinstance(row, dict) and row.get("lastPrice") is not None:
            return _ticker_from_binance(canonical, base, quote, row)
        return _demo_ticker(canonical)
    except Exception as exc:
        logger.warning(f"market_data.get_ticker fallback to demo: {exc}")
        return _demo_ticker(canonical)


async def build_candles(symbol: str, count: int = 44) -> list[Candle]:
    """K 线序列（Binance klines 1h，失败回退 demo）。"""
    try:
        rows = await _get_json(
            f"{_rest_base()}/api/v3/klines",
            {"symbol": _exchange_symbol(symbol), "interval": "1h", "limit": count},
        )
        if not isinstance(rows, list) or not rows:
            return _demo_candles(symbol, count)
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
        logger.warning(f"market_data.build_candles fallback to demo: {exc}")
        return _demo_candles(symbol, count)


async def get_order_book(symbol: str, depth: int = 9) -> OrderBookSnapshot:
    """订单簿快照（Binance depth，失败回退 demo）。"""
    try:
        data = await _get_json(
            f"{_rest_base()}/api/v3/depth", {"symbol": _exchange_symbol(symbol), "limit": max(depth, 5)}
        )
        raw_asks = data.get("asks", [])[:depth]
        raw_bids = data.get("bids", [])[:depth]
        if not raw_asks or not raw_bids:
            return _demo_order_book(symbol, depth)

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
        logger.warning(f"market_data.get_order_book fallback to demo: {exc}")
        return _demo_order_book(symbol, depth)


async def get_trade_tape(symbol: str, count: int = 12) -> list[TradeTick]:
    """成交流（Binance recent trades，失败回退 demo）。"""
    try:
        rows = await _get_json(
            f"{_rest_base()}/api/v3/trades", {"symbol": _exchange_symbol(symbol), "limit": count}
        )
        if not isinstance(rows, list) or not rows:
            return _demo_trade_tape(symbol, count)
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
        logger.warning(f"market_data.get_trade_tape fallback to demo: {exc}")
        return _demo_trade_tape(symbol, count)


async def get_top_movers(limit: int = 3) -> tuple[list[MarketTicker], list[MarketTicker]]:
    """涨幅榜与跌幅榜（基于真实 list_tickers）。"""
    tickers = await list_tickers()
    gainers = sorted([t for t in tickers if t.change_pct >= 0], key=lambda t: t.change_pct, reverse=True)
    losers = sorted([t for t in tickers if t.change_pct < 0], key=lambda t: t.change_pct)
    return gainers[:limit], losers[:limit]


async def get_heatmap() -> list[tuple[str, float]]:
    """热力图（真实 24h 涨跌幅，失败回退 demo 值）。"""
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
    """市场总览（CoinGecko global + alternative.me 情绪，任一失败该项回退）。"""
    fallback = _demo_overview()
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
        logger.warning(f"market_data.get_market_overview global fallback: {exc}")
        total_market_cap = fallback.total_market_cap
        volume_24h = fallback.volume_24h
        total_market_cap_change_pct = fallback.total_market_cap_change_pct
        btc_dominance = fallback.btc_dominance

    fear_greed = fallback.fear_greed
    fear_greed_label = fallback.fear_greed_label
    try:
        fng = (await _get_json(_FNG_URL))["data"][0]
        fear_greed = int(fng["value"])
        fear_greed_label = _fng_label(str(fng.get("value_classification", "")))
    except Exception as exc:
        logger.warning(f"market_data.get_market_overview fng fallback: {exc}")

    return MarketOverview(
        total_market_cap=total_market_cap,
        total_market_cap_change_pct=total_market_cap_change_pct,
        volume_24h=volume_24h,
        volume_24h_change_pct=fallback.volume_24h_change_pct,
        btc_dominance=btc_dominance,
        btc_dominance_change_pct=fallback.btc_dominance_change_pct,
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
        generated_at=datetime.now(UTC).strftime("%H:%M"),
    )
    return ticker, snapshot
