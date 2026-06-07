"""Freqtrade 编排 + 容器运行时集成 stub。

返回拟真 mock 数据；函数签名按真实编排预留：真实实现时这里会调用容器编排
（启动/停止/重启 Freqtrade 容器）、Freqtrade REST API（拉取交易、持仓、日志）。
当前阶段不创建任何真实容器、不下任何真实订单，金额与成交全为模拟。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

__all__ = (
    "BotRuntimeStatus",
    "ContainerOpResult",
    "LogEntry",
    "PositionSnapshot",
    "TradeRecord",
    "fetch_logs",
    "fetch_positions",
    "fetch_trades",
    "restart_bot",
    "start_bot",
    "stop_bot",
)


@dataclass(slots=True)
class ContainerOpResult:
    """容器生命周期操作结果（start / stop / restart）。"""

    ok: bool
    container_id: str
    runtime_status: str
    message: str


@dataclass(slots=True)
class BotRuntimeStatus:
    """机器人运行时聚合状态。"""

    runtime_status: str
    open_trades: int
    today_pnl_pct: float
    heartbeat_at: datetime


@dataclass(slots=True)
class TradeRecord:
    """单笔交易记录（mock）。"""

    pair: str
    side: str
    open_price: float
    close_price: float
    amount: float
    pnl_amount: float
    pnl_pct: float
    opened_at: datetime
    closed_at: datetime
    duration: str


@dataclass(slots=True)
class PositionSnapshot:
    """单个持仓快照（mock）。"""

    pair: str
    side: str
    open_price: float
    current_price: float
    amount: float
    value_usdt: float
    unrealized_pnl_amount: float
    unrealized_pnl_pct: float
    stop_loss_price: float


@dataclass(slots=True)
class LogEntry:
    """单条 Freqtrade 日志（mock）。"""

    timestamp: datetime
    level: str
    message: str
    metadata: dict[str, str] = field(default_factory=dict)


def start_bot(container_ref: str | None, run_mode: str) -> ContainerOpResult:
    """启动机器人容器（mock）。真实实现：编排器拉起 Freqtrade 容器并加载配置。"""
    return ContainerOpResult(
        ok=True,
        container_id=container_ref or "ctr_7f3a",
        runtime_status="running",
        message=f"已启动 · {run_mode}",
    )


def stop_bot(container_ref: str | None) -> ContainerOpResult:
    """停止机器人容器（mock）。真实实现：优雅停止容器，保留持仓快照。"""
    return ContainerOpResult(
        ok=True,
        container_id=container_ref or "ctr_7f3a",
        runtime_status="stopped",
        message="已停止",
    )


def restart_bot(container_ref: str | None) -> ContainerOpResult:
    """重启机器人容器（mock）。真实实现：重建容器，短暂中断后恢复。"""
    return ContainerOpResult(
        ok=True,
        container_id=container_ref or "ctr_7f3a",
        runtime_status="running",
        message="正在重启",
    )


def fetch_trades(container_ref: str | None, limit: int = 50) -> list[TradeRecord]:
    """拉取交易历史（mock）。真实实现：调用 Freqtrade REST /trades。"""
    base = datetime.now(UTC)
    samples = [
        ("BTC/USDT", "long", 67420.0, 68610.0, 0.18, 214.0, 1.8, "5h 12m"),
        ("BTC/USDT", "long", 66980.0, 67580.0, 0.20, 120.0, 0.9, "3h 02m"),
        ("BTC/USDT", "long", 67200.0, 66390.0, 0.19, -154.0, -1.2, "2h 48m"),
        ("BTC/USDT", "long", 65800.0, 67380.0, 0.21, 332.0, 2.4, "6h 20m"),
        ("BTC/USDT", "long", 66100.0, 66500.0, 0.20, 80.0, 0.6, "4h 05m"),
    ]
    records: list[TradeRecord] = []
    for index, (pair, side, open_price, close_price, amount, pnl_amount, pnl_pct, duration) in enumerate(samples):
        opened_at = base - timedelta(hours=6 * (index + 1))
        records.append(
            TradeRecord(
                pair=pair,
                side=side,
                open_price=open_price,
                close_price=close_price,
                amount=amount,
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
                opened_at=opened_at,
                closed_at=opened_at + timedelta(hours=3),
                duration=duration,
            )
        )
    return records[:limit]


def fetch_positions(container_ref: str | None) -> list[PositionSnapshot]:
    """拉取当前持仓（mock）。真实实现：调用 Freqtrade REST /status。"""
    return [
        PositionSnapshot(
            pair="BTC/USDT",
            side="long",
            open_price=67420.0,
            current_price=68610.0,
            amount=0.32,
            value_usdt=21955.0,
            unrealized_pnl_amount=380.0,
            unrealized_pnl_pct=1.8,
            stop_loss_price=63375.0,
        ),
        PositionSnapshot(
            pair="BTC/USDT",
            side="long",
            open_price=68050.0,
            current_price=68610.0,
            amount=0.13,
            value_usdt=8919.0,
            unrealized_pnl_amount=73.0,
            unrealized_pnl_pct=0.8,
            stop_loss_price=63967.0,
        ),
    ]


def fetch_logs(container_ref: str | None, level: str | None = None, limit: int = 100) -> list[LogEntry]:
    """拉取容器日志（mock）。真实实现：读取容器 stdout 或 Freqtrade REST /logs。"""
    base = datetime.now(UTC)
    samples = [
        ("INFO", "Bot heartbeat OK · open_trades=2"),
        ("TRADE", "Entry filled BTC/USDT long 0.13 @ 68,050"),
        ("INFO", "Signal confirmed by risk check · approved"),
        ("TRADE", "Exit filled BTC/USDT long 0.18 @ 68,610 (+1.8%)"),
        ("INFO", "Strategy populate_entry_trend · 1 candidate"),
        ("WARN", "Volatility above threshold · position size reduced"),
        ("TRADE", "Entry filled BTC/USDT long 0.20 @ 66,980"),
        ("INFO", "Daily report generated · PnL +0.9%"),
    ]
    entries = [
        LogEntry(timestamp=base - timedelta(minutes=12 * index), level=lvl, message=msg)
        for index, (lvl, msg) in enumerate(samples)
    ]
    if level and level.upper() != "ALL":
        entries = [entry for entry in entries if entry.level == level.upper()]
    return entries[:limit]
