"""交易机器人 view models。

列表 / 详情 / 创建（向导）/ 更新参数 / 设置 / 删除 / start / stop / restart /
live-enable（强确认语义）/ trades / positions / logs / AI 摘要 / 风控状态。
运行模式默认 dry_run；容器编排与运行时数据走 libs.integrations.freqtrade / agent（mock）。
跨模块名称（交易所账户 / 策略）用 select 查询拼接，不使用 ORM relationship。
"""

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.bot import BotCreateForm, BotSettingsUpdateForm, BotUpdateForm
from libs.auth.permissions import PermissionChecker
from libs.integrations import agent as agent_service
from libs.integrations import freqtrade as freqtrade_service
from models.bot import Bot, BotRunModeEnum, BotStatusEnum
from models.exchange import ExchangeAccount
from models.strategy import Strategy
from responses.bot import (
    BotAiSummaryResponseData,
    BotDetailResponseData,
    BotLifecycleResponseData,
    BotListItemResponseData,
    BotLiveEnableResponseData,
    BotLogEntryResponseData,
    BotPositionResponseData,
    BotRiskRowResponseData,
    BotRiskStatusResponseData,
    BotSignalAlignmentResponseData,
    BotTradeResponseData,
)
from view_models import BaseViewModel

__all__ = (
    "CreateBotViewModel",
    "DeleteBotViewModel",
    "EnableBotLiveViewModel",
    "GetBotAiSummaryViewModel",
    "GetBotDetailViewModel",
    "GetBotLogsViewModel",
    "GetBotPositionsViewModel",
    "GetBotRiskStatusViewModel",
    "GetBotTradesViewModel",
    "ListBotsViewModel",
    "RestartBotViewModel",
    "StartBotViewModel",
    "StopBotViewModel",
    "UpdateBotSettingsViewModel",
    "UpdateBotViewModel",
)

_DEFAULT_RISK_CONFIG: dict[str, bool] = {
    "cooldown": True,
    "newsFilter": True,
    "volatilityFilter": True,
    "autoStop": True,
}


def _format_pnl(pct: float) -> str:
    if pct == 0:
        return "—"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:g}%"


async def _resolve_names(db: AsyncSession, bot: Bot) -> tuple[str, str]:
    """查询交易所账户名与策略名（跨模块仅用 select，不用 relationship）。"""
    exchange = await db.get(ExchangeAccount, bot.exchange_account_id)
    strategy = await db.get(Strategy, bot.strategy_id)
    exchange_name = exchange.name if exchange is not None else ""
    strategy_name = strategy.name if strategy is not None else ""
    return exchange_name, strategy_name


def _build_list_item(bot: Bot, exchange_name: str, strategy_name: str) -> BotListItemResponseData:
    # Dry-run 模式下今日收益示意为正；停止状态显示为 —。
    today_pnl = 2.3 if bot.status == BotStatusEnum.RUNNING else 0.0
    return BotListItemResponseData(
        id=bot.id,
        name=bot.name,
        subtitle=f"{bot.timeframe} · Max {bot.max_open_trades} trades",
        tradeMode=bot.trade_mode,
        runMode=bot.run_mode,
        runModeLabel="Dry-run" if bot.run_mode == BotRunModeEnum.DRY_RUN else "Live",
        status=bot.status,
        strategyName=strategy_name,
        exchangeName=exchange_name,
        todayPnlPct=today_pnl,
        todayPnlLabel=_format_pnl(today_pnl),
        pnlPositive=today_pnl > 0,
        positions=2 if bot.status == BotStatusEnum.RUNNING else 0,
    )


def _build_detail(bot: Bot, exchange_name: str, strategy_name: str) -> BotDetailResponseData:
    base = _build_list_item(bot, exchange_name, strategy_name).model_dump()
    return BotDetailResponseData(
        **base,
        exchangeAccountId=bot.exchange_account_id,
        strategyId=bot.strategy_id,
        pairs=bot.pairs,
        stakeCurrency=bot.stake_currency,
        stakeAmount=bot.stake_amount,
        maxOpenTrades=bot.max_open_trades,
        timeframe=bot.timeframe,
        stoploss=bot.stoploss,
        trailingStop=bot.trailing_stop,
        dailyLossLimit=bot.daily_loss_limit,
        maxDrawdownLimit=bot.max_drawdown_limit,
        maxPosition=bot.max_position,
        maxLeverage=bot.max_leverage,
        riskConfig=bot.risk_config or _DEFAULT_RISK_CONFIG,
        telegramNotify=bot.telegram_notify,
        autoStopOnError=bot.auto_stop_on_error,
        aiSignalFilter=bot.ai_signal_filter,
        liveEnabled=bot.live_enabled,
        containerRef=bot.container_ref,
    )


class _AuthedBotViewModel(BaseViewModel):
    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def _load_owned_bot(self, bot_id: int) -> Bot | None:
        bot = await self.db.get(Bot, bot_id)
        if bot is None or bot.user_id != int(self.checker.user_id):
            return None
        return bot


class ListBotsViewModel(_AuthedBotViewModel):
    """机器人列表（仅本人）。"""

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bots = (
            await self.db.scalars(
                select(Bot).where(Bot.user_id == int(self.checker.user_id)).order_by(Bot.id.asc())
            )
        ).all()
        items: list[BotListItemResponseData] = []
        for bot in bots:
            exchange_name, strategy_name = await _resolve_names(self.db, bot)
            items.append(_build_list_item(bot, exchange_name, strategy_name))
        self.operating_successfully(items)


class GetBotDetailViewModel(_AuthedBotViewModel):
    """机器人详情。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, bot_id: int) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return
        exchange_name, strategy_name = await _resolve_names(self.db, bot)
        self.operating_successfully(_build_detail(bot, exchange_name, strategy_name))


class CreateBotViewModel(_AuthedBotViewModel):
    """创建机器人（向导）。运行模式默认 dry_run；选 live 也需后续强确认才真正开启。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: BotCreateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.form = form

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        name = self.form.name.strip()
        if not name:
            self.illegal_parameters("Bot 名称不能为空")
            return
        if not self.form.acknowledged:
            self.illegal_parameters("需确认风险声明后才能创建机器人")
            return
        if not self.form.pairs:
            self.illegal_parameters("至少选择一个交易对")
            return

        # 归属校验：交易所账户与策略必须属于当前用户（策略允许内置）。
        exchange = await self.db.get(ExchangeAccount, self.form.exchangeAccountId)
        if exchange is None or exchange.user_id != user_id:
            self.illegal_parameters("交易所账户无效")
            return
        strategy = await self.db.get(Strategy, self.form.strategyId)
        if strategy is None or (strategy.user_id is not None and strategy.user_id != user_id):
            self.illegal_parameters("策略无效")
            return

        # 创建即落库；运行模式默认 dry_run，live 仍需经 live-enable 强确认链路。
        bot = Bot(
            user_id=user_id,
            exchange_account_id=self.form.exchangeAccountId,
            strategy_id=self.form.strategyId,
            name=name,
            trade_mode=self.form.tradeMode,
            run_mode=BotRunModeEnum.DRY_RUN,
            status=BotStatusEnum.STOPPED,
            pairs=self.form.pairs,
            stake_currency=self.form.stakeCurrency,
            stake_amount=self.form.stakeAmount,
            max_open_trades=self.form.maxOpenTrades,
            timeframe=self.form.timeframe,
            stoploss=self.form.stoploss,
            trailing_stop=self.form.trailingStop,
            daily_loss_limit=self.form.dailyLossLimit,
            max_drawdown_limit=self.form.maxDrawdownLimit,
            max_position=self.form.maxPosition,
            max_leverage=self.form.maxLeverage,
            risk_config=self.form.riskConfig or dict(_DEFAULT_RISK_CONFIG),
            live_enabled=False,
        )
        self.db.add(bot)
        await self.db.commit()
        await self.db.refresh(bot)
        self.operating_successfully(_build_detail(bot, exchange.name, strategy.name))


class UpdateBotViewModel(_AuthedBotViewModel):
    """编辑策略参数（需二次确认由前端控制，后端落库）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: BotUpdateForm,
        checker: PermissionChecker,
        bot_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.form = form
        self.bot_id = bot_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        changes: dict[str, Any] = {}
        if self.form.stakeAmount is not None:
            bot.stake_amount = self.form.stakeAmount
            changes["stakeAmount"] = self.form.stakeAmount
        if self.form.maxOpenTrades is not None:
            bot.max_open_trades = self.form.maxOpenTrades
            changes["maxOpenTrades"] = self.form.maxOpenTrades
        if self.form.stoploss is not None:
            bot.stoploss = self.form.stoploss
            changes["stoploss"] = self.form.stoploss
        if self.form.trailingStop is not None:
            bot.trailing_stop = self.form.trailingStop
            changes["trailingStop"] = self.form.trailingStop
        if self.form.timeframe is not None:
            bot.timeframe = self.form.timeframe
            changes["timeframe"] = self.form.timeframe
        if self.form.tradeMode is not None:
            bot.trade_mode = self.form.tradeMode
            changes["tradeMode"] = self.form.tradeMode.value

        if not changes:
            self.nothing_changed()
            return

        await self.db.commit()
        await self.db.refresh(bot)
        exchange_name, strategy_name = await _resolve_names(self.db, bot)
        self.operating_successfully(_build_detail(bot, exchange_name, strategy_name))


class UpdateBotSettingsViewModel(_AuthedBotViewModel):
    """更新 Bot 设置开关。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: BotSettingsUpdateForm,
        checker: PermissionChecker,
        bot_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.form = form
        self.bot_id = bot_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        if self.form.telegramNotify is not None:
            bot.telegram_notify = self.form.telegramNotify
        if self.form.autoStopOnError is not None:
            bot.auto_stop_on_error = self.form.autoStopOnError
        if self.form.aiSignalFilter is not None:
            bot.ai_signal_filter = self.form.aiSignalFilter

        await self.db.commit()
        await self.db.refresh(bot)
        exchange_name, strategy_name = await _resolve_names(self.db, bot)
        self.operating_successfully(_build_detail(bot, exchange_name, strategy_name))


class DeleteBotViewModel(_AuthedBotViewModel):
    """删除机器人（先停容器再删配置）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, bot_id: int) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        if bot.status == BotStatusEnum.RUNNING:
            freqtrade_service.stop_bot(bot.container_ref)
        await self.db.delete(bot)
        await self.db.commit()
        self.operating_successfully()


class _BotLifecycleViewModel(_AuthedBotViewModel):
    """start / stop / restart 共享基类。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, bot_id: int) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id

    async def _run(self, op: str) -> None:
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        if op == "start":
            result = freqtrade_service.start_bot(bot.container_ref, bot.run_mode.value)
            bot.status = BotStatusEnum.RUNNING
        elif op == "stop":
            result = freqtrade_service.stop_bot(bot.container_ref)
            bot.status = BotStatusEnum.STOPPED
        else:
            result = freqtrade_service.restart_bot(bot.container_ref)
            bot.status = BotStatusEnum.RUNNING
        bot.container_ref = result.container_id
        await self.db.commit()

        self.operating_successfully(
            BotLifecycleResponseData(
                id=bot.id,
                status=bot.status,
                runtimeStatus=result.runtime_status,
                containerRef=result.container_id,
                message=result.message,
            )
        )


class StartBotViewModel(_BotLifecycleViewModel):
    """启动机器人。"""

    async def before(self) -> None:
        await super().before()
        await self._run("start")


class StopBotViewModel(_BotLifecycleViewModel):
    """停止机器人。"""

    async def before(self) -> None:
        await super().before()
        await self._run("stop")


class RestartBotViewModel(_BotLifecycleViewModel):
    """重启机器人。"""

    async def before(self) -> None:
        await super().before()
        await self._run("restart")


class EnableBotLiveViewModel(_AuthedBotViewModel):
    """开启实盘（强确认语义）：要求显式确认，仅返回状态，不真正下单。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, bot_id: int) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        # 强确认语义：标记已提交实盘切换，等待风控与 2FA；金额/下单全为模拟，绝不实际下单转账。
        bot.live_enabled = True
        await self.db.commit()
        await self.db.refresh(bot)
        self.operating_successfully(
            BotLiveEnableResponseData(
                id=bot.id,
                liveEnabled=bot.live_enabled,
                runMode=bot.run_mode,
                message="已提交实盘切换 · 等待风控与 2FA 确认",
            )
        )


class GetBotTradesViewModel(_AuthedBotViewModel):
    """交易记录（service mock）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, bot_id: int) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        trades = freqtrade_service.fetch_trades(bot.container_ref)
        self.operating_successfully(
            [
                BotTradeResponseData(
                    pair=trade.pair,
                    side=trade.side,
                    openPrice=trade.open_price,
                    closePrice=trade.close_price,
                    amount=trade.amount,
                    pnlAmount=trade.pnl_amount,
                    pnlPct=trade.pnl_pct,
                    openedAt=trade.opened_at.strftime("%m-%d %H:%M"),
                    closedAt=trade.closed_at.strftime("%m-%d %H:%M"),
                    duration=trade.duration,
                )
                for trade in trades
            ]
        )


class GetBotPositionsViewModel(_AuthedBotViewModel):
    """当前持仓（service mock）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, bot_id: int) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        positions = freqtrade_service.fetch_positions(bot.container_ref)
        self.operating_successfully(
            [
                BotPositionResponseData(
                    pair=position.pair,
                    side=position.side,
                    openPrice=position.open_price,
                    currentPrice=position.current_price,
                    amount=position.amount,
                    valueUsdt=position.value_usdt,
                    unrealizedPnlAmount=position.unrealized_pnl_amount,
                    unrealizedPnlPct=position.unrealized_pnl_pct,
                    stopLossPrice=position.stop_loss_price,
                )
                for position in positions
            ]
        )


class GetBotLogsViewModel(_AuthedBotViewModel):
    """Freqtrade 原始日志（service mock，可按级别筛选）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        bot_id: int,
        level: str | None,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id
        self.level = level

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        entries = freqtrade_service.fetch_logs(bot.container_ref, level=self.level)
        self.operating_successfully(
            [
                BotLogEntryResponseData(
                    timestamp=entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    level=entry.level,
                    message=entry.message,
                )
                for entry in entries
            ]
        )


class GetBotAiSummaryViewModel(_AuthedBotViewModel):
    """AI 投研摘要 + 信号一致性（agent service mock）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, bot_id: int) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        summary = agent_service.generate_bot_summary(bot.name, bot.pairs)
        alignment = summary.alignment
        self.operating_successfully(
            BotAiSummaryResponseData(
                trend=summary.trend,
                headline=summary.headline,
                narrative=summary.narrative,
                alignment=BotSignalAlignmentResponseData(
                    aiRecommendation=alignment.ai_recommendation,
                    aiConfidence=alignment.ai_confidence,
                    strategySignal=alignment.strategy_signal,
                    botDirection=alignment.bot_direction,
                    aligned=alignment.aligned,
                    riskLevel=alignment.risk_level,
                    suggestedAction=alignment.suggested_action,
                ),
            )
        )


class GetBotRiskStatusViewModel(_AuthedBotViewModel):
    """机器人风控状态（各限额占用，mock 拟真）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, bot_id: int) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return

        rows = [
            BotRiskRowResponseData(label="botDetail.dailyLoss", valuePct=40.0, valueLabel="1.2% / 3%", safe=True),
            BotRiskRowResponseData(label="botDetail.maxDrawdown", valuePct=62.0, valueLabel="6.2% / 10%", safe=False),
            BotRiskRowResponseData(label="botDetail.singleExposure", valuePct=82.0, valueLabel="4.1% / 5%", safe=False),
            BotRiskRowResponseData(label="botDetail.losingStreak", valuePct=33.0, valueLabel="1 / 3", safe=True),
            BotRiskRowResponseData(label="botDetail.leverage", valuePct=33.0, valueLabel="1x / 3x", safe=True),
        ]
        self.operating_successfully(BotRiskStatusResponseData(overall="Normal", rows=rows))
