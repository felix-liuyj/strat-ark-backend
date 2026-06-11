"""Dashboard 聚合 ViewModel。"""

from datetime import datetime, time
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth.permissions import PermissionChecker
from models.ai import AgentReport
from models.bot import Bot, BotRunModeEnum, BotStatusEnum
from models.exchange import ExchangeAccount
from models.notification import Notification
from models.risk import RiskEvent, RiskRule, RiskRuleTypeEnum
from models.signals import Signal
from models.strategy import Strategy
from models.trade import Position, Trade, TradeStatusEnum
from responses.dashboard import (
    DashboardAiSummaryResponseData,
    DashboardBotResponseData,
    DashboardMetricResponseData,
    DashboardOverviewResponseData,
    DashboardPositionResponseData,
    DashboardRiskLimitResponseData,
    DashboardRiskStatusResponseData,
    DashboardSignalResponseData,
    DashboardTopbarResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = ("GetDashboardOverviewViewModel",)

_RISK_LIMIT_LABELS = {
    RiskRuleTypeEnum.DAILY_LOSS_LIMIT: ("dailyLoss", "dashboard.dailyLossLimit"),
    RiskRuleTypeEnum.MAX_DRAWDOWN: ("maxDrawdown", "dashboard.maxDrawdownLimit"),
    RiskRuleTypeEnum.MAX_POSITION_SIZE: ("singleExposure", "dashboard.singleExposure"),
    RiskRuleTypeEnum.COOLDOWN: ("losingStreak", "dashboard.losingStreak"),
}
_RISK_LIMIT_TYPES = tuple(_RISK_LIMIT_LABELS)
_RISK_LEVEL_KEYS = {"high": "strategy.riskHigh", "low": "strategy.riskLow", "medium": "strategy.riskMed"}


class GetDashboardOverviewViewModel(BaseViewModel):
    """Dashboard 页面聚合入口。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        overview = await _build_overview(self.db, int(self.checker.user_id))
        self.operating_successfully(overview)


async def _build_overview(db: AsyncSession, user_id: int) -> DashboardOverviewResponseData:
    stats = await _build_metric_inputs(db, user_id)
    return DashboardOverviewResponseData(
        topbar=await _build_topbar(db, user_id, stats),
        risk=await _build_risk(db, user_id),
        metrics=_build_metrics(stats),
        aiSummary=await _build_ai_summary(db, user_id),
        bots=await _build_bots(db, user_id),
        signals=await _build_signals(db, user_id),
        positions=await _build_positions(db, user_id),
    )


async def _build_metric_inputs(db: AsyncSession, user_id: int) -> dict[str, float]:
    total_equity = await _sum_float(db, ExchangeAccount.balance_usdt, ExchangeAccount.user_id == user_id)
    today_pnl = await _today_pnl(db, user_id)
    total_bots = await _count_bots(db, user_id)
    running_bots = await _count_bots(db, user_id, Bot.status == BotStatusEnum.RUNNING)
    win_rate = await _win_rate(db, user_id)
    return {
        "total_equity": total_equity,
        "today_pnl": today_pnl,
        "today_pnl_pct": _pct_of(today_pnl, total_equity),
        "total_bots": total_bots,
        "running_bots": running_bots,
        "win_rate": win_rate,
    }


async def _build_topbar(db: AsyncSession, user_id: int, stats: dict[str, float]) -> DashboardTopbarResponseData:
    live_bots = await _count_bots(db, user_id, Bot.run_mode == BotRunModeEnum.LIVE)
    unread = await _count_notifications(db, user_id)
    return DashboardTopbarResponseData(
        totalEquity=stats["total_equity"],
        totalEquityLabel=_money_label(stats["total_equity"]),
        todayPnlPct=stats["today_pnl_pct"],
        todayPnlLabel=_pct_label(stats["today_pnl_pct"]),
        mode="live" if live_bots else "dry",
        unreadNotifications=unread,
    )


async def _build_risk(db: AsyncSession, user_id: int) -> DashboardRiskStatusResponseData:
    unresolved = await _count_risk_events(db, user_id)
    return DashboardRiskStatusResponseData(
        status="degraded" if unresolved else "healthy",
        headlineKey="dashboard.systemAttention" if unresolved else "dashboard.systemNormal",
        statusKey="status.degraded" if unresolved else "dashboard.systemHealthy",
        limits=await _build_risk_limits(db, user_id),
    )


async def _build_ai_summary(db: AsyncSession, user_id: int) -> DashboardAiSummaryResponseData:
    report = await db.scalar(
        select(AgentReport).where(AgentReport.user_id == user_id).order_by(AgentReport.created_at.desc()).limit(1)
    )
    if report is None:
        return DashboardAiSummaryResponseData(bias="", confidencePct=0, updatedLabel="", summary="", focusSymbols=[])
    return DashboardAiSummaryResponseData(
        bias=report.market_state or report.signal or "",
        confidencePct=round(report.confidence * 100),
        updatedLabel=report.created_at.strftime("%m-%d %H:%M"),
        summary=report.summary,
        focusSymbols=[report.symbol] if report.symbol else [],
    )


def _build_metrics(stats: dict[str, float]) -> list[DashboardMetricResponseData]:
    return [
        _metric(
            "totalEquity", "dashboard.totalEquity", stats["total_equity"],
            _money_label(stats["total_equity"]), _money_label(stats["today_pnl"]), "brand",
        ),
        _metric(
            "todayPnl", "dashboard.todayPnl", stats["today_pnl_pct"],
            _pct_label(stats["today_pnl_pct"]), _money_label(stats["today_pnl"]), "positive",
        ),
        _metric(
            "activeBots", "dashboard.activeBots", stats["running_bots"],
            f"{int(stats['running_bots'])} / {int(stats['total_bots'])}", str(int(stats["running_bots"])), "brand",
        ),
        _metric(
            "winRate", "dashboard.winRate", stats["win_rate"],
            _pct_label(stats["win_rate"]), "dashboard.closedTrades", "positive",
        ),
    ]


def _metric(
    key: str,
    label_key: str,
    value: float,
    value_label: str,
    change_label: str,
    tone: str,
) -> DashboardMetricResponseData:
    return DashboardMetricResponseData(
        key=key,
        labelKey=label_key,
        value=value,
        valueLabel=value_label,
        changeLabel=change_label,
        tone=tone,
        sparkline=[value, value],
    )


async def _build_bots(db: AsyncSession, user_id: int) -> list[DashboardBotResponseData]:
    bots = list((await db.scalars(select(Bot).where(Bot.user_id == user_id).order_by(Bot.id.asc()).limit(3))).all())
    metrics = await _position_metrics(db, user_id)
    return [await _bot_response(db, bot, metrics.get(bot.id, (0, 0.0))) for bot in bots]


async def _bot_response(db: AsyncSession, bot: Bot, metrics: tuple[int, float]) -> DashboardBotResponseData:
    positions_count, pnl = metrics
    exchange = await db.get(ExchangeAccount, bot.exchange_account_id)
    strategy_name = await _strategy_name(db, bot.strategy_id)
    subtitle = " · ".join(part for part in (strategy_name, exchange.name if exchange else "", bot.timeframe) if part)
    return DashboardBotResponseData(
        id=str(bot.id),
        icon=_bot_icon(strategy_name),
        name=bot.name,
        subtitle=subtitle,
        status=str(bot.status),
        pnlLabel=_money_label(pnl),
        positionsCount=positions_count,
    )


async def _strategy_name(db: AsyncSession, strategy_id: int) -> str:
    strategy = await db.get(Strategy, strategy_id)
    return strategy.name if strategy is not None else ""


async def _build_signals(db: AsyncSession, user_id: int) -> list[DashboardSignalResponseData]:
    statement = select(Signal).where(Signal.user_id == user_id).order_by(Signal.created_at.desc()).limit(6)
    return [_signal_response(signal) for signal in (await db.scalars(statement)).all()]


def _signal_response(signal: Signal) -> DashboardSignalResponseData:
    return DashboardSignalResponseData(
        id=str(signal.id),
        time=signal.created_at.strftime("%H:%M"),
        symbol=signal.symbol,
        direction=signal.direction,
        source=signal.source,
        confidenceLabel=_confidence_label(signal.confidence),
        riskLevelKey=_RISK_LEVEL_KEYS.get(signal.risk_level, "strategy.riskMed"),
        status=signal.status,
    )


async def _build_positions(db: AsyncSession, user_id: int) -> list[DashboardPositionResponseData]:
    statement = select(Position).where(Position.user_id == user_id).order_by(Position.id.desc()).limit(10)
    return [_position_response(position) for position in (await db.scalars(statement)).all()]


def _position_response(position: Position) -> DashboardPositionResponseData:
    return DashboardPositionResponseData(
        symbol=position.symbol,
        direction=str(position.side),
        entryPriceLabel=_number_label(position.open_price),
        markPriceLabel=_number_label(position.current_price),
        sizeLabel=_number_label(position.quantity),
        valueLabel=_money_label(position.position_value),
        pnlLabel=f"{_money_label(position.unrealized_pnl)} ({_pct_label(position.unrealized_pnl_pct)})",
        botName=position.bot_name,
    )


async def _build_risk_limits(db: AsyncSession, user_id: int) -> list[DashboardRiskLimitResponseData]:
    statement = select(RiskRule).where(RiskRule.user_id == user_id, RiskRule.rule_type.in_(_RISK_LIMIT_TYPES))
    rules = (await db.scalars(statement.order_by(RiskRule.id.asc()))).all()
    return [_risk_limit(rule) for rule in rules if rule.rule_type in _RISK_LIMIT_LABELS]


def _risk_limit(rule: RiskRule) -> DashboardRiskLimitResponseData:
    key, label_key = _RISK_LIMIT_LABELS[RiskRuleTypeEnum(rule.rule_type)]
    current = _limit_label(rule.current_value, rule.unit)
    limit = _limit_label(rule.limit_value, rule.unit)
    safe = rule.limit_value is None or rule.current_value is None or rule.current_value <= rule.limit_value
    return DashboardRiskLimitResponseData(
        key=key,
        labelKey=label_key,
        currentLabel=current,
        limitLabel=limit,
        safe=safe,
    )


async def _sum_float(db: AsyncSession, column: Any, *where: Any) -> float:
    value = await db.scalar(select(func.coalesce(func.sum(column), 0.0)).where(*where))
    return float(value or 0.0)


async def _today_pnl(db: AsyncSession, user_id: int) -> float:
    today_start = datetime.combine(datetime.now().date(), time.min)
    return await _sum_float(db, Trade.pnl, Trade.user_id == user_id, Trade.created_at >= today_start)


async def _win_rate(db: AsyncSession, user_id: int) -> float:
    closed = Trade.status == TradeStatusEnum.CLOSED
    total = await _count_trades(db, user_id, closed)
    wins = await _count_trades(db, user_id, closed, Trade.pnl >= 0)
    return round(wins / total * 100, 2) if total else 0.0


async def _count_bots(db: AsyncSession, user_id: int, *where: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(Bot).where(Bot.user_id == user_id, *where)) or 0)


async def _count_trades(db: AsyncSession, user_id: int, *where: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(Trade).where(Trade.user_id == user_id, *where)) or 0)


async def _count_notifications(db: AsyncSession, user_id: int) -> int:
    stmt = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id,
        Notification.is_read.is_(False),
    )
    return int(await db.scalar(stmt) or 0)


async def _count_risk_events(db: AsyncSession, user_id: int) -> int:
    stmt = select(func.count()).select_from(RiskEvent).where(
        RiskEvent.user_id == user_id,
        RiskEvent.resolved.is_(False),
    )
    return int(await db.scalar(stmt) or 0)


async def _position_metrics(db: AsyncSession, user_id: int) -> dict[int, tuple[int, float]]:
    rows = await db.execute(
        select(Position.bot_id, func.count(), func.coalesce(func.sum(Position.unrealized_pnl), 0.0))
        .where(Position.user_id == user_id)
        .group_by(Position.bot_id)
    )
    return {int(bot_id): (int(count), float(pnl)) for bot_id, count, pnl in rows if bot_id is not None}


def _pct_of(value: float, base: float) -> float:
    return round(value / base * 100, 2) if base else 0.0


def _money_label(value: float) -> str:
    prefix = "-" if value < 0 else ""
    return f"{prefix}${abs(value):,.2f}"


def _pct_label(value: float) -> str:
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value:.2f}%"


def _number_label(value: float) -> str:
    return f"{value:,.8g}"


def _limit_label(value: float | None, unit: str) -> str:
    return "—" if value is None else f"{_number_label(value)}{unit}"


def _confidence_label(value: float) -> str:
    pct = value * 100 if value <= 1 else value
    return f"{round(pct)}%"


def _bot_icon(strategy_name: str) -> str:
    name = strategy_name.lower()
    if "mean" in name or "rsi" in name:
        return "mean"
    if "break" in name or "donchian" in name:
        return "breakout"
    return "trend"
