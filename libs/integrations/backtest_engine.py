"""轻量回测引擎。

基于真实行情 K 线执行买入并持有基线回测，用于当前同步回测接口。这里不生成演示
行情；行情源不可用时抛出业务异常，由 ViewModel 保存失败任务并返回错误。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from statistics import mean, pstdev

from libs.integrations import market_data

__all__ = (
    "BacktestDataUnavailableError",
    "BacktestRunResult",
    "DailyReturnPoint",
    "DrawdownPoint",
    "EquityPoint",
    "PairReturn",
    "run_backtest",
)


@dataclass(frozen=True)
class EquityPoint:
    x: int
    value: float


@dataclass(frozen=True)
class DrawdownPoint:
    x: int
    value: float


@dataclass(frozen=True)
class DailyReturnPoint:
    day: int
    value: float


@dataclass(frozen=True)
class PairReturn:
    name: str
    value: float


@dataclass(frozen=True)
class BacktestRunResult:
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
    equity_curve: list[EquityPoint]
    drawdown_curve: list[DrawdownPoint]
    daily_returns: list[DailyReturnPoint]
    pair_returns: list[PairReturn]


class BacktestDataUnavailableError(RuntimeError):
    """历史行情不可用，不能执行真实回测。"""


def _pct(value: float) -> float:
    return round(value * 100, 4)


def _safe_ratio(upside: float, downside: float) -> float:
    if downside == 0:
        return round(upside, 4) if upside > 0 else 0.0
    return round(upside / abs(downside), 4)


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    volatility = pstdev(returns)
    if volatility == 0:
        return 0.0
    return round(mean(returns) / volatility * math.sqrt(len(returns)), 4)


def _cagr(initial_balance: float, final_balance: float, first_ts: int, last_ts: int) -> float:
    if final_balance <= 0:
        return -100.0
    years = max((last_ts - first_ts) / 86400 / 365, 1 / 365)
    return _pct((final_balance / initial_balance) ** (1 / years) - 1)


def _daily_returns(closes: list[float], cost_rate: float) -> list[DailyReturnPoint]:
    points: list[DailyReturnPoint] = []
    for index, (previous, current) in enumerate(pairwise(closes), start=1):
        if previous <= 0:
            continue
        points.append(DailyReturnPoint(day=index, value=_pct((current - previous) / previous - cost_rate)))
    return points


def _equity_and_drawdown(
    closes: list[float],
    initial_balance: float,
    cost_rate: float,
) -> tuple[list[EquityPoint], list[DrawdownPoint]]:
    units = initial_balance * (1 - cost_rate) / closes[0]
    peak = initial_balance
    equity_points: list[EquityPoint] = []
    drawdown_points: list[DrawdownPoint] = []
    for index, close in enumerate(closes):
        value = round(units * close * (1 - cost_rate), 4)
        peak = max(peak, value)
        drawdown = (value - peak) / peak if peak > 0 else 0.0
        equity_points.append(EquityPoint(x=index, value=value))
        drawdown_points.append(DrawdownPoint(x=index, value=_pct(drawdown)))
    return equity_points, drawdown_points


async def run_backtest(
    *,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    initial_balance: float,
    fee_rate: float,
    slippage_rate: float,
) -> BacktestRunResult:
    """执行真实行情回测。

    当前策略源码尚未接入 Freqtrade 回测进程，因此这里使用真实 K 线上的买入并持有基线
    产出可审计指标；后续接入 Freqtrade 时保持同一结果 DTO 即可。
    """
    del strategy_name, start_date, end_date
    candles = await market_data.build_candles(symbol, count=240, interval=timeframe)
    if len(candles) < 2:
        raise BacktestDataUnavailableError("无法获取真实历史行情，回测任务未执行")

    cost_rate = max(fee_rate, 0.0) + max(slippage_rate, 0.0)
    closes = [candle.close for candle in candles if candle.close > 0]
    if len(closes) < 2:
        raise BacktestDataUnavailableError("历史行情数据不足，回测任务未执行")

    equity_curve, drawdown_curve = _equity_and_drawdown(closes, initial_balance, cost_rate)
    daily_returns = _daily_returns(closes, cost_rate)
    positives = [point.value for point in daily_returns if point.value > 0]
    negatives = [point.value for point in daily_returns if point.value < 0]
    final_balance = equity_curve[-1].value
    total_return = _pct((final_balance - initial_balance) / initial_balance)
    pair = PairReturn(name=symbol.upper(), value=total_return)

    first_ts = candles[0].ts
    last_ts = candles[-1].ts
    duration_hours = max((last_ts - first_ts) / 3600, 0.0)
    trade_count = max(len(daily_returns), 1)

    return BacktestRunResult(
        total_return=total_return,
        cagr=_cagr(initial_balance, final_balance, first_ts, last_ts),
        max_drawdown=min((point.value for point in drawdown_curve), default=0.0),
        sharpe=_sharpe([point.value for point in daily_returns]),
        win_rate=round(len(positives) / len(daily_returns) * 100, 4) if daily_returns else 0.0,
        profit_factor=_safe_ratio(sum(positives), sum(negatives)),
        avg_duration_hours=round(duration_hours / trade_count, 4),
        trades=trade_count,
        best_pair=pair.name,
        worst_pair=pair.name,
        final_balance=final_balance,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        daily_returns=daily_returns,
        pair_returns=[pair],
    )
