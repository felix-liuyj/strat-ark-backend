"""交易机器人 view models。

列表 / 详情 / 创建（向导）/ 更新参数 / 设置 / 删除 / start / stop / restart /
live-enable（强确认语义）/ trades / positions / logs / AI 摘要 / 风控状态。
运行模式默认 dry_run。

编排模式：start 经 freqtrade orchestrator 为该 bot 拉起独立实例容器（配置与凭证经
``FREQTRADE__*`` 环境变量注入，交易所明文凭证仅 live 时解密传递、不落盘）；
trades / positions / logs 走实例自身 REST。编排器未配置或调用失败返回业务错误，
无 mock 回退。跨模块名称（交易所账户 / 策略）用 select 查询拼接，不使用 ORM relationship。
"""

import json
import secrets
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.bot import BotCreateForm, BotSettingsUpdateForm, BotUpdateForm
from libs.auth.permissions import PermissionChecker
from libs.crypto import decrypt_text, encrypt_text
from libs.integrations import agent as agent_service
from libs.integrations import freqtrade as freqtrade_service
from libs.integrations.freqtrade import FreqtradeUnavailableError
from models.account import PlanEnum
from models.bot import Bot, BotRunModeEnum, BotStatusEnum, BotTradeModeEnum
from models.engine import EngineKindEnum, get_engine_connection_config
from models.exchange import ExchangeAccount, ExchangePermissionEnum
from models.settings import SystemConfig, SystemConfigGroupEnum
from models.strategy import Strategy
from models.user import User
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
from view_models.common.base import BaseViewModel

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


_CREDENTIALS_UNAVAILABLE = "交易所凭证不可用，请在交易所账户页重新录入 API Key 与 Secret"
_INSTANCE_CREDENTIALS_BROKEN = "实例访问凭证不可用，请重新启动机器人"


async def _load_orchestrator(db: AsyncSession) -> freqtrade_service.OrchestratorConfig:
    """读取引擎管理页落库的 freqtrade 编排器配置（单一事实源）。"""
    return freqtrade_service.resolve_orchestrator_config(
        await get_engine_connection_config(db, EngineKindEnum.FREQTRADE)
    )


def _instance_ref(bot: Bot) -> str:
    return f"stratark-bot-{bot.id}"


def _instance_credentials(bot: Bot) -> freqtrade_service.InstanceCredentials | None:
    """还原 bot 实例 REST 访问信息；凭证缺失 / 解密失败返回 None。"""
    if not bot.api_url or not bot.api_username:
        return None
    password = decrypt_text(bot.api_password_cipher)
    if not password:
        return None
    return freqtrade_service.InstanceCredentials(
        api_url=bot.api_url, username=bot.api_username, password=password
    )


def _parse_pct(value: str) -> float | None:
    """把 "-6%" / "1.5%" 形式解析为小数比例（-0.06 / 0.015）；不可解析返回 None。"""
    raw = (value or "").strip().rstrip("%").strip()
    if not raw:
        return None
    try:
        return float(raw) / 100
    except ValueError:
        return None


async def _two_factor_state(db: AsyncSession, user_id: int) -> dict:
    """读取用户 2FA 设置（system_configs general/twoFactor，与 user_center 同源）。"""
    row = await db.scalar(
        select(SystemConfig).where(
            SystemConfig.user_id == user_id,
            SystemConfig.group == SystemConfigGroupEnum.GENERAL,
            SystemConfig.key == "twoFactor",
        )
    )
    return dict(row.value) if row is not None and isinstance(row.value, dict) else {}


def _build_instance_env(
    bot: Bot,
    account: ExchangeAccount,
    *,
    exchange_key: str | None,
    exchange_secret: str | None,
    api_username: str,
    api_password: str,
) -> dict[str, str]:
    """组装实例容器环境变量（freqtrade 原生 FREQTRADE__ 覆盖机制）。

    交易所明文凭证仅 live 注入；api_server 凭证随实例生成，backend 持有加密副本。
    """
    is_live = bot.run_mode == BotRunModeEnum.LIVE
    env: dict[str, str] = {
        "FREQTRADE__BOT_NAME": bot.name or _instance_ref(bot),
        "FREQTRADE__DRY_RUN": "false" if is_live else "true",
        "FREQTRADE__TRADING_MODE": "futures" if bot.trade_mode == BotTradeModeEnum.FUTURES else "spot",
        "FREQTRADE__EXCHANGE__NAME": account.provider.value,
        "FREQTRADE__EXCHANGE__PAIR_WHITELIST": json.dumps(list(bot.pairs or [])),
        "FREQTRADE__STAKE_CURRENCY": bot.stake_currency,
        "FREQTRADE__STAKE_AMOUNT": str(bot.stake_amount),
        "FREQTRADE__MAX_OPEN_TRADES": str(bot.max_open_trades),
        "FREQTRADE__TIMEFRAME": bot.timeframe,
        "FREQTRADE__API_SERVER__ENABLED": "true",
        "FREQTRADE__API_SERVER__LISTEN_IP_ADDRESS": "0.0.0.0",
        "FREQTRADE__API_SERVER__LISTEN_PORT": "8080",
        "FREQTRADE__API_SERVER__USERNAME": api_username,
        "FREQTRADE__API_SERVER__PASSWORD": api_password,
        "FREQTRADE__API_SERVER__JWT_SECRET_KEY": secrets.token_hex(32),
    }
    if bot.trade_mode == BotTradeModeEnum.FUTURES:
        env["FREQTRADE__MARGIN_MODE"] = "isolated"
    stoploss = _parse_pct(bot.stoploss)
    if stoploss is not None:
        env["FREQTRADE__STOPLOSS"] = str(-abs(stoploss))
    trailing = _parse_pct(bot.trailing_stop)
    if trailing is not None and trailing > 0:
        env["FREQTRADE__TRAILING_STOP"] = "true"
        env["FREQTRADE__TRAILING_STOP_POSITIVE"] = str(trailing)
    if is_live and exchange_key and exchange_secret:
        env["FREQTRADE__EXCHANGE__KEY"] = exchange_key
        env["FREQTRADE__EXCHANGE__SECRET"] = exchange_secret
    return env


async def _resolve_names(db: AsyncSession, bot: Bot) -> tuple[str, str]:
    """查询交易所账户名与策略名（跨模块仅用 select，不用 relationship）。"""
    exchange = await db.get(ExchangeAccount, bot.exchange_account_id)
    strategy = await db.get(Strategy, bot.strategy_id)
    exchange_name = exchange.name if exchange is not None else ""
    strategy_name = strategy.name if strategy is not None else ""
    return exchange_name, strategy_name


def _build_list_item(
    bot: Bot, exchange_name: str, strategy_name: str, *, today_pnl: float = 0.0, positions: int = 0
) -> BotListItemResponseData:
    # 列表页轻量化：运行时指标（今日收益 / 持仓数）默认占位 0 / —，
    # 真实数据在详情页经实例 REST 拉取（列表逐 bot 探实例代价过高）。
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
        positions=positions,
        pairs=bot.pairs,
    )


def _build_detail(bot: Bot, exchange_name: str, strategy_name: str) -> BotDetailResponseData:
    base = _build_list_item(bot, exchange_name, strategy_name).model_dump()
    return BotDetailResponseData(
        **base,
        exchangeAccountId=bot.exchange_account_id,
        strategyId=bot.strategy_id,
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

        if bot.container_ref:
            orchestrator = await _load_orchestrator(self.db)
            try:
                instance = await freqtrade_service.get_instance(orchestrator, bot.container_ref)
                if instance is not None:
                    await freqtrade_service.remove_instance(orchestrator, bot.container_ref)
            except FreqtradeUnavailableError as exc:
                # 实例可能仍在运行：编排器不可达时拒绝删除，避免泄漏脱管的运行实例。
                self.operating_failed(f"{exc}；为避免实例脱管，请先恢复编排器后再删除")
                return
        await self.db.delete(bot)
        await self.db.commit()
        self.operating_successfully()


class _BotLifecycleViewModel(_AuthedBotViewModel):
    """start / stop / restart 共享基类（经编排器操作实例容器）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker, bot_id: int) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.bot_id = bot_id

    def _respond(self, bot: Bot, runtime_status: str, message: str) -> None:
        self.operating_successfully(
            BotLifecycleResponseData(
                id=bot.id,
                status=bot.status,
                runtimeStatus=runtime_status,
                containerRef=bot.container_ref,
                message=message,
            )
        )

    async def _check_live_gates(self, bot: Bot, account: ExchangeAccount) -> bool:
        """live 启动硬门槛：实盘确认 / 套餐 / 2FA / API Key 权限。失败时已写响应。"""
        if not bot.live_enabled:
            self.illegal_parameters("请先在 Bot 详情完成实盘开启确认")
            return False
        user = await self.db.get(User, int(self.checker.user_id))
        if user is None or user.plan == PlanEnum.FREE:
            self.forbidden("免费套餐不支持实盘交易，请升级订阅")
            return False
        two_factor = await _two_factor_state(self.db, int(self.checker.user_id))
        if bool(two_factor.get("requireForLiveActions", True)) and not bool(two_factor.get("totpEnabled", False)):
            self.operating_failed("实盘操作要求两步验证，请先在用户中心开启 2FA")
            return False
        if account.permission == ExchangePermissionEnum.READ_TRADE_WITHDRAW or not account.withdraw_disabled:
            self.forbidden("该 API Key 含提现权限，禁止用于实盘；请更换为仅交易权限的 Key")
            return False
        return True

    async def _start(self, bot: Bot) -> None:
        orchestrator = await _load_orchestrator(self.db)
        strategy = await self.db.get(Strategy, bot.strategy_id)
        if strategy is None or not strategy.freqtrade_class:
            self.illegal_parameters("该策略暂无可执行实现，无法启动实例")
            return
        account = await self.db.get(ExchangeAccount, bot.exchange_account_id)
        if account is None:
            self.illegal_parameters("绑定的交易所账户不存在")
            return

        exchange_key: str | None = None
        exchange_secret: str | None = None
        if bot.run_mode == BotRunModeEnum.LIVE:
            if not await self._check_live_gates(bot, account):
                return
            exchange_key = decrypt_text(account.api_key_cipher)
            exchange_secret = decrypt_text(account.api_secret_cipher)
            if not exchange_key or not exchange_secret:
                self.operating_failed(_CREDENTIALS_UNAVAILABLE)
                return

        # 实例 api_server 凭证随启动重新生成，密码仅以密文留存。
        api_username = f"bot{bot.id}"
        api_password = secrets.token_urlsafe(24)
        env = _build_instance_env(
            bot,
            account,
            exchange_key=exchange_key,
            exchange_secret=exchange_secret,
            api_username=api_username,
            api_password=api_password,
        )
        try:
            info = await freqtrade_service.create_instance(
                orchestrator, ref=_instance_ref(bot), strategy=strategy.freqtrade_class, env=env
            )
        except FreqtradeUnavailableError as exc:
            self.operating_failed(str(exc))
            return

        bot.container_ref = info.ref
        bot.api_url = f"http://{info.ref}:8080"
        bot.api_username = api_username
        bot.api_password_cipher = encrypt_text(api_password)
        bot.status = BotStatusEnum.RUNNING
        await self.db.commit()
        self._respond(bot, info.status, f"实例已启动 · {bot.run_mode.value}")

    async def _stop(self, bot: Bot) -> None:
        orchestrator = await _load_orchestrator(self.db)
        if bot.container_ref:
            try:
                instance = await freqtrade_service.get_instance(orchestrator, bot.container_ref)
                if instance is not None:
                    await freqtrade_service.stop_instance(orchestrator, bot.container_ref)
            except FreqtradeUnavailableError as exc:
                self.operating_failed(str(exc))
                return
        bot.status = BotStatusEnum.STOPPED
        await self.db.commit()
        self._respond(bot, "stopped", "实例已停止")

    async def _restart(self, bot: Bot) -> None:
        orchestrator = await _load_orchestrator(self.db)
        if not bot.container_ref:
            self.illegal_parameters("实例尚未创建，请直接启动")
            return
        try:
            info = await freqtrade_service.restart_instance(orchestrator, bot.container_ref)
        except FreqtradeUnavailableError as exc:
            self.operating_failed(str(exc))
            return
        bot.status = BotStatusEnum.RUNNING
        await self.db.commit()
        self._respond(bot, info.status, "实例重启中")


class StartBotViewModel(_BotLifecycleViewModel):
    """启动机器人（编排器拉起独立实例；live 需通过全部硬门槛）。"""

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return
        await self._start(bot)


class StopBotViewModel(_BotLifecycleViewModel):
    """停止机器人（停实例容器，保留以便快速恢复）。"""

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return
        await self._stop(bot)


class RestartBotViewModel(_BotLifecycleViewModel):
    """重启机器人实例。"""

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        bot = await self._load_owned_bot(self.bot_id)
        if bot is None:
            self.not_found("机器人不存在")
            return
        await self._restart(bot)


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

        # 强确认语义：仅标记实盘授权；真实门槛（套餐 / 2FA / API Key 权限 / 凭证可用）
        # 在启动实例时逐项校验，任一不满足拒绝启动。
        bot.live_enabled = True
        bot.run_mode = BotRunModeEnum.LIVE
        await self.db.commit()
        await self.db.refresh(bot)
        self.operating_successfully(
            BotLiveEnableResponseData(
                id=bot.id,
                liveEnabled=bot.live_enabled,
                runMode=bot.run_mode,
                message="实盘已授权 · 启动时将校验套餐、两步验证与 API Key 权限",
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

        # 停机实例无运行数据：返回空列表（非伪造）；运行中实例走真实 REST。
        creds = _instance_credentials(bot)
        if bot.status != BotStatusEnum.RUNNING or creds is None:
            self.operating_successfully([])
            return
        try:
            trades = await freqtrade_service.fetch_trades(creds)
        except FreqtradeUnavailableError as exc:
            self.operating_failed(str(exc))
            return
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

        creds = _instance_credentials(bot)
        if bot.status != BotStatusEnum.RUNNING or creds is None:
            self.operating_successfully([])
            return
        try:
            positions = await freqtrade_service.fetch_positions(creds)
        except FreqtradeUnavailableError as exc:
            self.operating_failed(str(exc))
            return
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

        creds = _instance_credentials(bot)
        if bot.status != BotStatusEnum.RUNNING or creds is None:
            self.operating_successfully([])
            return
        try:
            entries = await freqtrade_service.fetch_logs(creds, level=self.level)
        except FreqtradeUnavailableError as exc:
            self.operating_failed(str(exc))
            return
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
