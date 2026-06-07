"""回测引擎集成 stub。

返回拟真 mock 数据；函数签名按真实回测引擎（如 vectorbt / Freqtrade backtesting）
预留：真实实现时这里会基于历史 K 线、策略信号、手续费与滑点逐笔撮合，产出绩效
指标、权益曲线、回撤序列、每日收益与交易对归因。当前阶段不读取真实行情、不撮合，
仅用确定性种子生成稳定可回放的拟真结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = (
    "BacktestRunResult",
    "DailyReturnPoint",
    "DrawdownPoint",
    "EquityPoint",
    "PairReturn",
    "run_backtest",
)


@dataclass(slots=True)
class EquityPoint:
    """权益曲线单点（x 为序号，value 为账户净值）。"""

    x: int
    value: float


@dataclass(slots=True)
class DrawdownPoint:
    """回撤曲线单点（value 为相对峰值的回撤百分比，负值）。"""

    x: int
    value: float


@dataclass(slots=True)
class DailyReturnPoint:
    """每日收益单点（对应前端热力图单元，value 为当日收益百分比）。"""

    day: int
    value: float


@dataclass(slots=True)
class PairReturn:
    """单交易对累计收益归因（百分比，带正负）。"""

    name: str
    value: float


@dataclass(slots=True)
class BacktestRunResult:
    """回测完整结果（绩效指标 + 各序列）。"""

    total_return: float
    cagr: float
    max_drawdown: float
    sharpe: float
    win_rate: float
    profit_factor: float
    avg_duration_hours: float
    trades: int
    best_pair: str
    worst_pair: str
    final_balance: float
    equity_curve: list[EquityPoint] = field(default_factory=list)
    drawdown_curve: list[DrawdownPoint] = field(default_factory=list)
    daily_returns: list[DailyReturnPoint] = field(default_factory=list)
    pair_returns: list[PairReturn] = field(default_factory=list)


def _seeded_rng(seed: int):
    """复刻前端确定性随机（线性同余），保证回测结果稳定可回放。"""
    state = seed

    def _next() -> float:
        nonlocal state
        state = (state * 9301 + 49297) % 233280
        return state / 233280

    return _next


def _build_daily_returns(rng) -> list[DailyReturnPoint]:
    """生成近 60 个交易日的每日收益（与前端 buildDailyCells 同口径，偏移 -0.42）。"""
    points: list[DailyReturnPoint] = []
    for i in range(60):
        value = round((rng() - 0.42) * 4, 2)
        points.append(DailyReturnPoint(day=i, value=value))
    return points


def _build_equity_and_drawdown(
    rng, initial_balance: float, fee_rate: float, slippage_rate: float
) -> tuple[list[EquityPoint], list[DrawdownPoint], float]:
    """生成权益曲线与回撤序列；手续费与滑点对净值施加确定性损耗。"""
    equity: list[EquityPoint] = []
    drawdown: list[DrawdownPoint] = []
    balance = initial_balance
    peak = initial_balance
    # 手续费/滑点在每根 bar 上以乘性损耗体现（mock 口径）。
    cost_drag = 1.0 - (fee_rate + slippage_rate)
    for i in range(60):
        step = (rng() - 0.4) * 0.018
        balance = round(balance * (1.0 + step) * cost_drag, 2)
        peak = max(peak, balance)
        dd = round((balance - peak) / peak * 100, 2) if peak else 0.0
        equity.append(EquityPoint(x=i, value=balance))
        drawdown.append(DrawdownPoint(x=i, value=dd))
    return equity, drawdown, balance


def run_backtest(
    strategy_name: str,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    initial_balance: float,
    fee_rate: float,
    slippage_rate: float,
) -> BacktestRunResult:
    """运行回测（mock，返回绩效指标 + 权益/回撤/每日收益/交易对序列）。

    真实实现：加载区间历史 K 线，按策略信号逐笔撮合（计入手续费与滑点），统计
    绩效指标与各序列。本 stub 用 symbol 长度派生种子，保证同输入稳定可回放。
    """
    seed = (sum(ord(c) for c in f"{strategy_name}{symbol}{timeframe}") % 97) + 13
    rng = _seeded_rng(seed)

    daily_returns = _build_daily_returns(_seeded_rng(seed))
    equity_curve, drawdown_curve, final_balance = _build_equity_and_drawdown(
        rng, initial_balance, fee_rate, slippage_rate
    )

    total_return = round((final_balance - initial_balance) / initial_balance * 100, 1)
    max_drawdown = round(min((p.value for p in drawdown_curve), default=0.0), 1)
    sharpe = round(1.2 + rng() * 0.9, 2)
    win_rate = round(50 + rng() * 12, 1)
    profit_factor = round(1.4 + rng() * 0.8, 2)
    avg_duration_hours = round(4 + rng() * 6, 1)
    trades = int(300 + rng() * 200)

    pair_returns = [
        PairReturn(name="BTC/USDT", value=14.2),
        PairReturn(name="ETH/USDT", value=6.8),
        PairReturn(name="SOL/USDT", value=4.1),
        PairReturn(name="LINK/USDT", value=1.2),
        PairReturn(name="DOGE/USDT", value=-2.5),
    ]
    best_pair = max(pair_returns, key=lambda p: p.value).name
    worst_pair = min(pair_returns, key=lambda p: p.value).name

    return BacktestRunResult(
        total_return=total_return,
        cagr=round(total_return * 0.71, 1),
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_duration_hours=avg_duration_hours,
        trades=trades,
        best_pair=best_pair,
        worst_pair=worst_pair,
        final_balance=final_balance,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        daily_returns=daily_returns,
        pair_returns=pair_returns,
    )
