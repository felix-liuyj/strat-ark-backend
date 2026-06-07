"""交易记录视图模型。

交易记录 / 持仓 / 未完成订单 / 统计来自交易 service（拟真），筛选与搜索在业务层完成；
CSV 导出返回 csv 文本由前端触发下载。取消挂单为写操作占位（service stub 直接成功）。
"""

import csv
import io

from fastapi import Request

from libs.auth.permissions import PermissionChecker
from libs.integrations import trading
from libs.integrations.trading import TradeRecord
from models.trade import OrderStatusEnum, OrderTypeEnum, TradeSideEnum, TradeStatusEnum
from responses.trade import (
    OpenOrderResponseData,
    PositionResponseData,
    TradeExportResponseData,
    TradeResponseData,
    TradeStatsResponseData,
)
from view_models import BaseViewModel

__all__ = (
    "CancelOrderViewModel",
    "ExportTradesViewModel",
    "ListOpenOrdersViewModel",
    "ListPositionsViewModel",
    "ListTradesViewModel",
    "TradeStatsViewModel",
)

# 交易记录筛选项（与前端 chips 单选语义对齐）。
_FILTER_ALL = "all"
_FILTER_OPEN = "open"
_FILTER_CLOSED = "closed"
_FILTER_PROFIT = "profit"
_FILTER_LOSS = "loss"
_VALID_FILTERS = {_FILTER_ALL, _FILTER_OPEN, _FILTER_CLOSED, _FILTER_PROFIT, _FILTER_LOSS}


def _side_enum(side: str) -> TradeSideEnum:
    return TradeSideEnum.SHORT if side.lower() == "short" else TradeSideEnum.LONG


def _trade_to_response(record: TradeRecord) -> TradeResponseData:
    return TradeResponseData(
        tradeRef=record.trade_ref,
        openedAt=record.opened_at,
        symbol=record.symbol,
        side=_side_enum(record.side),
        botName=record.bot_name,
        openPrice=record.open_price,
        closePrice=record.close_price,
        quantity=record.quantity,
        pnl=record.pnl,
        pnlPct=record.pnl_pct,
        duration=record.duration,
        status=TradeStatusEnum.OPEN if record.status == "open" else TradeStatusEnum.CLOSED,
    )


def _matches(record: TradeRecord, query: str, status_filter: str, bots: set[str] | None) -> bool:
    if query and query not in record.symbol.lower():
        return False
    if bots is not None and record.bot_name not in bots:
        return False
    if status_filter == _FILTER_OPEN:
        return record.status == "open"
    if status_filter == _FILTER_CLOSED:
        return record.status == "closed"
    if status_filter == _FILTER_PROFIT:
        return record.pnl >= 0
    if status_filter == _FILTER_LOSS:
        return record.pnl < 0
    return True


class ListTradesViewModel(BaseViewModel):
    """交易记录列表（支持交易对搜索 + 状态筛选 + Bot 多选）。"""

    def __init__(
        self,
        request: Request,
        checker: PermissionChecker,
        query: str,
        status_filter: str,
        bots: str | None,
    ) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.query = query.strip().lower()
        self.status_filter = status_filter if status_filter in _VALID_FILTERS else _FILTER_ALL
        # bots 为逗号分隔 Bot 名；为空表示不过滤。
        self.bots = {b.strip() for b in bots.split(",") if b.strip()} if bots else None

    async def before(self) -> None:
        self.checker.require_auth()
        records = trading.list_trades()
        filtered = [r for r in records if _matches(r, self.query, self.status_filter, self.bots)]
        self.operating_successfully([_trade_to_response(r) for r in filtered])


class ListPositionsViewModel(BaseViewModel):
    """当前持仓列表（开仓价 / 现价 / 数量 / 持仓价值 / 未实现盈亏）。"""

    def __init__(self, request: Request, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker

    async def before(self) -> None:
        self.checker.require_auth()
        positions = trading.list_positions()
        data = [
            PositionResponseData(
                positionRef=p.position_ref,
                symbol=p.symbol,
                side=_side_enum(p.side),
                botName=p.bot_name,
                openPrice=p.open_price,
                currentPrice=p.current_price,
                quantity=p.quantity,
                positionValue=p.position_value,
                unrealizedPnl=p.unrealized_pnl,
                unrealizedPnlPct=p.unrealized_pnl_pct,
            )
            for p in positions
        ]
        self.operating_successfully(data)


class ListOpenOrdersViewModel(BaseViewModel):
    """未完成订单列表（挂单）。"""

    def __init__(self, request: Request, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker

    async def before(self) -> None:
        self.checker.require_auth()
        orders = trading.list_open_orders()
        data = [
            OpenOrderResponseData(
                orderRef=o.order_ref,
                symbol=o.symbol,
                side=_side_enum(o.side),
                botName=o.bot_name,
                orderType=OrderTypeEnum(o.order_type.lower()),
                status=OrderStatusEnum(o.status.lower()),
                price=o.price,
                quantity=o.quantity,
                filledPct=o.filled_pct,
                createdAt=o.created_at,
            )
            for o in orders
        ]
        self.operating_successfully(data)


class TradeStatsViewModel(BaseViewModel):
    """交易统计 KPI（总交易 / 胜率 / 盈亏比 / 净盈亏）。"""

    def __init__(self, request: Request, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker

    async def before(self) -> None:
        self.checker.require_auth()
        stats = trading.summarize_trades()
        data = TradeStatsResponseData(
            totalTrades=stats.total_trades,
            winCount=stats.win_count,
            lossCount=stats.loss_count,
            winRate=stats.win_rate,
            profitFactor=stats.profit_factor,
            netPnl=stats.net_pnl,
            netPnlPct=stats.net_pnl_pct,
            window=stats.extra.get("window", ""),
        )
        self.operating_successfully(data)


class ExportTradesViewModel(BaseViewModel):
    """导出交易记录为 CSV 文本（前端负责触发下载）。"""

    def __init__(self, request: Request, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker

    @staticmethod
    def _build_csv(records: list[TradeRecord]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["time", "symbol", "side", "bot", "open", "close", "qty", "pnl", "pnlPct", "duration", "status"]
        )
        for r in records:
            writer.writerow(
                [
                    r.opened_at,
                    r.symbol,
                    r.side,
                    r.bot_name,
                    r.open_price,
                    "" if r.close_price is None else r.close_price,
                    r.quantity,
                    r.pnl,
                    r.pnl_pct,
                    r.duration,
                    r.status,
                ]
            )
        return buffer.getvalue()

    async def before(self) -> None:
        self.checker.require_auth()
        records = trading.list_trades()
        data = TradeExportResponseData(
            filename="trades.csv",
            contentType="text/csv",
            csv=self._build_csv(records),
        )
        self.operating_successfully(data)


class CancelOrderViewModel(BaseViewModel):
    """取消未完成订单（service stub 直接成功，真实实现会调用交易所撤单）。"""

    def __init__(self, request: Request, checker: PermissionChecker, order_id: str) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.order_id = order_id

    async def before(self) -> None:
        self.checker.require_auth()
        orders = trading.list_open_orders()
        target = next((o for o in orders if o.order_ref == self.order_id), None)
        if target is None:
            self.not_found("订单不存在或已完成")
            return
        # 真实实现：调用 Freqtrade / 交易所撤单端点；当前 stub 仅校验存在性即成功。
        self.operating_successfully()
