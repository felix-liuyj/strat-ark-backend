"""交易记录视图模型。

交易记录 / 持仓 / 统计来自用户运行中 bot 的 freqtrade 实例 REST 聚合：
遍历本人 RUNNING 且实例凭证可用的 bot，并发拉取已平仓成交与当前持仓后合并。
单个实例不可达时跳过该 bot（记日志，不伪造数据、不整体失败）；停机用户无数据即空。
CSV 导出由前端触发下载；未完成挂单 freqtrade 无独立来源，返回空；取消挂单不支持。
"""

import asyncio
import csv
import io

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth.permissions import PermissionChecker
from libs.crypto import decrypt_text
from libs.integrations import freqtrade as ft
from libs.logger import logger
from models.bot import Bot, BotStatusEnum
from models.trade import TradeSideEnum, TradeStatusEnum
from responses.trade import (
    PositionResponseData,
    TradeExportResponseData,
    TradeResponseData,
    TradeStatsResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = (
    "CancelOrderViewModel",
    "ExportTradesViewModel",
    "ListOpenOrdersViewModel",
    "ListPositionsViewModel",
    "ListTradesViewModel",
    "TradeStatsViewModel",
)

_FILTER_ALL = "all"
_FILTER_OPEN = "open"
_FILTER_CLOSED = "closed"
_FILTER_PROFIT = "profit"
_FILTER_LOSS = "loss"
_VALID_FILTERS = {_FILTER_ALL, _FILTER_OPEN, _FILTER_CLOSED, _FILTER_PROFIT, _FILTER_LOSS}


def _side_enum(side: str) -> TradeSideEnum:
    return TradeSideEnum.SHORT if side.lower() == "short" else TradeSideEnum.LONG


def _instance_credentials(bot: Bot) -> ft.InstanceCredentials | None:
    if not bot.api_url or not bot.api_username:
        return None
    password = decrypt_text(bot.api_password_cipher)
    if not password:
        return None
    return ft.InstanceCredentials(api_url=bot.api_url, username=bot.api_username, password=password)


async def _running_instances(db: AsyncSession, user_id: int) -> list[tuple[Bot, ft.InstanceCredentials]]:
    """本人 RUNNING 且实例凭证可用的 (bot, creds) 列表。"""
    bots = (
        await db.scalars(
            select(Bot)
            .where(Bot.user_id == user_id, Bot.status == BotStatusEnum.RUNNING)
            .order_by(Bot.id.asc())
        )
    ).all()
    pairs: list[tuple[Bot, ft.InstanceCredentials]] = []
    for bot in bots:
        creds = _instance_credentials(bot)
        if creds is not None:
            pairs.append((bot, creds))
    return pairs


async def _gather(instances: list[tuple[Bot, ft.InstanceCredentials]], coro_factory) -> list[tuple[Bot, list]]:
    """对每个实例并发执行 coro_factory(creds)，单实例失败跳过（记日志）。"""
    if not instances:
        return []
    results = await asyncio.gather(
        *(coro_factory(creds) for _, creds in instances), return_exceptions=True
    )
    out: list[tuple[Bot, list]] = []
    for (bot, _), result in zip(instances, results, strict=True):
        if isinstance(result, Exception):
            logger.warning(f"trades 聚合：bot={bot.id} 实例不可达，已跳过：{result}")
            continue
        out.append((bot, result))
    return out


async def _collect_closed_trades(db: AsyncSession, user_id: int) -> list[tuple[Bot, ft.TradeRecord]]:
    instances = await _running_instances(db, user_id)
    collected = await _gather(instances, lambda c: ft.fetch_trades(c))
    rows = [(bot, trade) for bot, trades in collected for trade in trades]
    rows.sort(key=lambda pair: pair[1].opened_at, reverse=True)
    return rows


async def _collect_positions(db: AsyncSession, user_id: int) -> list[tuple[Bot, ft.PositionSnapshot]]:
    instances = await _running_instances(db, user_id)
    collected = await _gather(instances, lambda c: ft.fetch_positions(c))
    return [(bot, pos) for bot, positions in collected for pos in positions]


def _closed_to_response(bot: Bot, trade: ft.TradeRecord) -> TradeResponseData:
    return TradeResponseData(
        tradeRef=f"{bot.id}-{trade.pair}-{int(trade.opened_at.timestamp())}",
        openedAt=trade.opened_at.strftime("%m-%d %H:%M"),
        symbol=trade.pair,
        side=_side_enum(trade.side),
        botName=bot.name,
        openPrice=trade.open_price,
        closePrice=trade.close_price,
        quantity=trade.amount,
        pnl=trade.pnl_amount,
        pnlPct=trade.pnl_pct,
        duration=trade.duration,
        status=TradeStatusEnum.CLOSED,
    )


def _position_to_trade_response(bot: Bot, pos: ft.PositionSnapshot) -> TradeResponseData:
    return TradeResponseData(
        tradeRef=f"{bot.id}-{pos.pair}-open",
        openedAt="",
        symbol=pos.pair,
        side=_side_enum(pos.side),
        botName=bot.name,
        openPrice=pos.open_price,
        closePrice=None,
        quantity=pos.amount,
        pnl=pos.unrealized_pnl_amount,
        pnlPct=pos.unrealized_pnl_pct,
        duration="持仓中",
        status=TradeStatusEnum.OPEN,
    )


class _AuthedTradesViewModel(BaseViewModel):
    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker


class ListTradesViewModel(_AuthedTradesViewModel):
    """交易记录列表（已平仓成交 + 当前持仓行），支持交易对搜索 + 状态筛选 + Bot 多选。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        query: str,
        status_filter: str,
        bots: str | None,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.query = query.strip().lower()
        self.status_filter = status_filter if status_filter in _VALID_FILTERS else _FILTER_ALL
        self.bots = {b.strip() for b in bots.split(",") if b.strip()} if bots else None

    def _matches(self, item: TradeResponseData) -> bool:
        if self.query and self.query not in item.symbol.lower():
            return False
        if self.bots is not None and item.botName not in self.bots:
            return False
        if self.status_filter == _FILTER_OPEN:
            return item.status == TradeStatusEnum.OPEN
        if self.status_filter == _FILTER_CLOSED:
            return item.status == TradeStatusEnum.CLOSED
        if self.status_filter == _FILTER_PROFIT:
            return item.pnl >= 0
        if self.status_filter == _FILTER_LOSS:
            return item.pnl < 0
        return True

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)
        items = [_position_to_trade_response(b, p) for b, p in await _collect_positions(self.db, user_id)]
        items += [_closed_to_response(b, t) for b, t in await _collect_closed_trades(self.db, user_id)]
        self.operating_successfully([item for item in items if self._matches(item)])


class ListPositionsViewModel(_AuthedTradesViewModel):
    """当前持仓列表（开仓价 / 现价 / 数量 / 持仓价值 / 未实现盈亏）。"""

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        positions = await _collect_positions(self.db, int(self.checker.user_id))
        self.operating_successfully(
            [
                PositionResponseData(
                    positionRef=f"{bot.id}-{pos.pair}",
                    symbol=pos.pair,
                    side=_side_enum(pos.side),
                    botName=bot.name,
                    openPrice=pos.open_price,
                    currentPrice=pos.current_price,
                    quantity=pos.amount,
                    positionValue=pos.value_usdt,
                    unrealizedPnl=pos.unrealized_pnl_amount,
                    unrealizedPnlPct=pos.unrealized_pnl_pct,
                )
                for bot, pos in positions
            ]
        )


class ListOpenOrdersViewModel(_AuthedTradesViewModel):
    """未完成订单列表：freqtrade 无独立挂单 REST 来源，返回空（不伪造）。"""

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        self.operating_successfully([])


class TradeStatsViewModel(_AuthedTradesViewModel):
    """交易统计 KPI：按本人全部运行实例的已平仓成交聚合。"""

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        rows = await _collect_closed_trades(self.db, int(self.checker.user_id))
        trades = [t for _, t in rows]
        total = len(trades)
        wins = [t for t in trades if t.pnl_amount >= 0]
        losses = [t for t in trades if t.pnl_amount < 0]
        gross_profit = sum(t.pnl_amount for t in wins)
        gross_loss = abs(sum(t.pnl_amount for t in losses))
        net_pnl = round(sum(t.pnl_amount for t in trades), 2)
        self.operating_successfully(
            TradeStatsResponseData(
                totalTrades=total,
                winCount=len(wins),
                lossCount=len(losses),
                winRate=round(len(wins) / total * 100, 1) if total else 0.0,
                profitFactor=round(gross_profit / gross_loss, 2) if gross_loss else 0.0,
                netPnl=net_pnl,
                netPnlPct=0.0,  # 组合收益率需本金口径，交易明细不足以精确计算，留 0
                window="运行实例成交",
            )
        )


class ExportTradesViewModel(_AuthedTradesViewModel):
    """导出已平仓交易记录为 CSV 文本（前端负责触发下载）。"""

    @staticmethod
    def _build_csv(rows: list[tuple[Bot, ft.TradeRecord]]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["time", "symbol", "side", "bot", "open", "close", "qty", "pnl", "pnlPct", "duration"])
        for bot, t in rows:
            writer.writerow(
                [
                    t.opened_at.strftime("%Y-%m-%d %H:%M"),
                    t.pair,
                    t.side,
                    bot.name,
                    t.open_price,
                    "" if t.close_price is None else t.close_price,
                    t.amount,
                    t.pnl_amount,
                    t.pnl_pct,
                    t.duration,
                ]
            )
        return buffer.getvalue()

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        rows = await _collect_closed_trades(self.db, int(self.checker.user_id))
        self.operating_successfully(
            TradeExportResponseData(filename="stratark-trades.csv", contentType="text/csv", csv=self._build_csv(rows))
        )


class CancelOrderViewModel(_AuthedTradesViewModel):
    """取消未完成订单：当前无挂单来源，统一返回订单不存在。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, order_id: str) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.order_id = order_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        self.not_found("订单不存在或已完成")
