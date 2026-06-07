"""交易记录 / 持仓 / 未完成订单 service stub（交易记录页专用）。

真实实现会从 Freqtrade REST API 与交易所成交回报聚合出完整交易明细、当前持仓与挂单。
当前阶段返回**拟真 mock**：与前端 trades/data.ts 的 TRADES 数据形状严格对齐，
便于交易记录页、持仓列表、未完成订单页联调。ViewModel 只调用这里的函数。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = (
    "OpenOrderRecord",
    "PositionRecord",
    "TradeRecord",
    "TradeStats",
    "list_open_orders",
    "list_positions",
    "list_trades",
    "list_trading_bots",
    "summarize_trades",
)


@dataclass(slots=True)
class TradeRecord:
    """单条交易记录（开仓 / 平仓 / 盈亏 / 时长）。"""

    trade_ref: str
    opened_at: str
    symbol: str
    side: str
    bot_name: str
    open_price: float
    close_price: float | None
    quantity: float
    pnl: float
    pnl_pct: float
    duration: str
    status: str


@dataclass(slots=True)
class PositionRecord:
    """单个持仓快照（开仓价 / 现价 / 数量 / 持仓价值 / 未实现盈亏）。"""

    position_ref: str
    symbol: str
    side: str
    bot_name: str
    open_price: float
    current_price: float
    quantity: float
    position_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


@dataclass(slots=True)
class OpenOrderRecord:
    """未完成订单（挂单）。"""

    order_ref: str
    symbol: str
    side: str
    bot_name: str
    order_type: str
    price: float
    quantity: float
    filled_pct: float
    created_at: str
    status: str


@dataclass(slots=True)
class TradeStats:
    """交易统计 KPI（总交易 / 胜率 / 盈亏比 / 净盈亏）。"""

    total_trades: int
    win_count: int
    loss_count: int
    win_rate: float
    profit_factor: float
    net_pnl: float
    net_pnl_pct: float
    extra: dict[str, str] = field(default_factory=dict)


# 拟真交易记录底表（与前端 TRADES 严格对齐，价格转为数值）。
_TRADES: list[dict[str, object]] = [
    {
        "ref": "T-1009",
        "at": "06-06 09:42",
        "sym": "BTC/USDT",
        "side": "Long",
        "bot": "BTC Trend Bot",
        "open": 67420.0,
        "close": 68610.0,
        "qty": 0.18,
        "pnl": 214.0,
        "pct": 1.8,
        "dur": "5h 12m",
        "status": "closed",
    },
    {
        "ref": "T-1010",
        "at": "06-06 10:28",
        "sym": "BTC/USDT",
        "side": "Long",
        "bot": "BTC Trend Bot",
        "open": 68050.0,
        "close": None,
        "qty": 0.13,
        "pnl": 73.0,
        "pct": 0.8,
        "dur": "持仓中",
        "status": "open",
    },
    {
        "ref": "T-1007",
        "at": "06-06 08:55",
        "sym": "ETH/USDT",
        "side": "Long",
        "bot": "ETH Mean Rev",
        "open": 3448.0,
        "close": 3512.0,
        "qty": 3.10,
        "pnl": 198.0,
        "pct": 1.9,
        "dur": "1h 40m",
        "status": "closed",
    },
    {
        "ref": "T-1004",
        "at": "06-06 04:10",
        "sym": "BTC/USDT",
        "side": "Long",
        "bot": "BTC Trend Bot",
        "open": 66980.0,
        "close": 67580.0,
        "qty": 0.20,
        "pnl": 120.0,
        "pct": 0.9,
        "dur": "3h 02m",
        "status": "closed",
    },
    {
        "ref": "T-1003",
        "at": "06-05 22:30",
        "sym": "BTC/USDT",
        "side": "Long",
        "bot": "BTC Trend Bot",
        "open": 67200.0,
        "close": 66390.0,
        "qty": 0.19,
        "pnl": -154.0,
        "pct": -1.2,
        "dur": "2h 48m",
        "status": "closed",
    },
    {
        "ref": "T-1002",
        "at": "06-05 19:12",
        "sym": "ETH/USDT",
        "side": "Long",
        "bot": "ETH Mean Rev",
        "open": 3402.0,
        "close": 3461.0,
        "qty": 2.90,
        "pnl": 171.0,
        "pct": 1.7,
        "dur": "2h 10m",
        "status": "closed",
    },
    {
        "ref": "T-1001",
        "at": "06-05 16:05",
        "sym": "BTC/USDT",
        "side": "Long",
        "bot": "BTC Trend Bot",
        "open": 65800.0,
        "close": 67380.0,
        "qty": 0.21,
        "pnl": 332.0,
        "pct": 2.4,
        "dur": "6h 20m",
        "status": "closed",
    },
    {
        "ref": "T-1000",
        "at": "06-05 12:40",
        "sym": "ETH/USDT",
        "side": "Short",
        "bot": "ETH Mean Rev",
        "open": 3520.0,
        "close": 3560.0,
        "qty": 2.80,
        "pnl": -112.0,
        "pct": -1.1,
        "dur": "1h 25m",
        "status": "closed",
    },
    {
        "ref": "T-0999",
        "at": "06-05 09:18",
        "sym": "BTC/USDT",
        "side": "Long",
        "bot": "BTC Trend Bot",
        "open": 66100.0,
        "close": 66500.0,
        "qty": 0.20,
        "pnl": 80.0,
        "pct": 0.6,
        "dur": "4h 05m",
        "status": "closed",
    },
]


def list_trades() -> list[TradeRecord]:
    """返回交易记录全表（开仓 + 平仓 + 持仓中）。

    真实实现：聚合 Freqtrade /trades 历史成交与当前持仓为统一明细。
    """
    return [
        TradeRecord(
            trade_ref=str(r["ref"]),
            opened_at=str(r["at"]),
            symbol=str(r["sym"]),
            side=str(r["side"]),
            bot_name=str(r["bot"]),
            open_price=float(r["open"]),  # type: ignore[arg-type]
            close_price=None if r["close"] is None else float(r["close"]),  # type: ignore[arg-type]
            quantity=float(r["qty"]),  # type: ignore[arg-type]
            pnl=float(r["pnl"]),  # type: ignore[arg-type]
            pnl_pct=float(r["pct"]),  # type: ignore[arg-type]
            duration=str(r["dur"]),
            status=str(r["status"]),
        )
        for r in _TRADES
    ]


def list_positions() -> list[PositionRecord]:
    """返回当前持仓（由 open 状态交易派生现价与未实现盈亏）。

    真实实现：调用 Freqtrade /status 取实时持仓与现价。
    """
    positions: list[PositionRecord] = []
    for record in list_trades():
        if record.status != "open":
            continue
        current_price = record.open_price * (1 + record.pnl_pct / 100)
        position_value = current_price * record.quantity
        positions.append(
            PositionRecord(
                position_ref=record.trade_ref,
                symbol=record.symbol,
                side=record.side,
                bot_name=record.bot_name,
                open_price=record.open_price,
                current_price=current_price,
                quantity=record.quantity,
                position_value=position_value,
                unrealized_pnl=record.pnl,
                unrealized_pnl_pct=record.pnl_pct,
            )
        )
    return positions


def list_open_orders() -> list[OpenOrderRecord]:
    """返回未完成订单（拟真挂单）。

    真实实现：读取交易所未成交挂单与 Freqtrade 排队中入场订单。
    """
    return [
        OpenOrderRecord(
            order_ref="O-2051",
            symbol="ETH/USDT",
            side="Long",
            bot_name="ETH Mean Rev",
            order_type="Limit",
            price=3480.0,
            quantity=2.50,
            filled_pct=0.0,
            created_at="06-06 10:31",
            status="pending",
        ),
        OpenOrderRecord(
            order_ref="O-2050",
            symbol="BTC/USDT",
            side="Long",
            bot_name="BTC Trend Bot",
            order_type="Limit",
            price=68200.0,
            quantity=0.12,
            filled_pct=35.0,
            created_at="06-06 10:18",
            status="partial",
        ),
    ]


def list_trading_bots() -> list[str]:
    """返回参与交易的机器人名称列表（供前端 Bot 多选筛选）。"""
    return ["BTC Trend Bot", "ETH Mean Rev"]


def summarize_trades() -> TradeStats:
    """返回交易统计 KPI（拟真静态值，与前端指标卡对齐）。

    真实实现：按近 30 天成交聚合胜率、盈亏比、净盈亏等指标。
    """
    return TradeStats(
        total_trades=312,
        win_count=179,
        loss_count=133,
        win_rate=57.4,
        profit_factor=1.92,
        net_pnl=32700.0,
        net_pnl_pct=13.2,
        extra={"window": "近 30 天", "gross_label": "毛利 / 毛损"},
    )
