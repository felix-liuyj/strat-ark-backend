"""Bot 实例守护后台任务：状态对账 + 日亏熔断。

lifespan 启动一个常驻协程，按固定间隔：
1. **状态对账**：对每个标记 RUNNING 的 bot 查询编排器实际容器状态，实例丢失 / 退出
   时把 Bot 纠偏为 STOPPED 并记 RiskEvent（前端风控页可见）。
2. **日亏熔断**：经实例 REST 读当日收益，跌破 ``daily_loss_limit`` 时强制停机
   （编排器 stop）+ RiskEvent（DANGER，action_taken 记录处置）。

编排器未配置时本轮静默跳过（平台尚未启用编排）；自持会话（new_async_session），
不复用请求级会话。
"""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import select

from libs.crypto import decrypt_text
from libs.integrations import freqtrade as freqtrade_service
from libs.integrations.freqtrade import FreqtradeUnavailableError
from libs.logger import logger
from models.bot import Bot, BotStatusEnum
from models.engine import EngineKindEnum, get_engine_connection_config
from models.risk import RiskEvent, RiskEventLevelEnum, RiskRuleScopeEnum, RiskRuleTypeEnum

__all__ = ("start_guardian", "stop_guardian")

_GUARD_INTERVAL_SECONDS = 60

_task: asyncio.Task | None = None


def _parse_pct(value: str) -> float | None:
    raw = (value or "").strip().rstrip("%").strip()
    if not raw:
        return None
    try:
        return float(raw) / 100
    except ValueError:
        return None


def _instance_credentials(bot: Bot) -> freqtrade_service.InstanceCredentials | None:
    if not bot.api_url or not bot.api_username:
        return None
    password = decrypt_text(bot.api_password_cipher)
    if not password:
        return None
    return freqtrade_service.InstanceCredentials(
        api_url=bot.api_url, username=bot.api_username, password=password
    )


def _risk_event(
    bot: Bot, *, level: RiskEventLevelEnum, title: str, description: str, action: str | None
) -> RiskEvent:
    return RiskEvent(
        user_id=bot.user_id,
        level=level,
        scope=RiskRuleScopeEnum.BOT,
        rule_type=RiskRuleTypeEnum.DAILY_LOSS_LIMIT if action else None,
        title=title,
        description=description[:255],
        bot_id=bot.id,
        action_taken=action,
        occurred_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
    )


async def _check_daily_loss(
    db, orchestrator: freqtrade_service.OrchestratorConfig, bot: Bot
) -> None:
    """日亏熔断：跌破 daily_loss_limit 强制停机并记 DANGER 事件。"""
    limit = _parse_pct(bot.daily_loss_limit)
    creds = _instance_credentials(bot)
    if limit is None or limit <= 0 or creds is None:
        return
    try:
        pnl_pct = await freqtrade_service.fetch_daily_profit_pct(creds)
    except FreqtradeUnavailableError:
        return  # 实例接口暂不可达（可能正在启动），下一轮再查。
    if pnl_pct > -abs(limit) * 100:
        return
    try:
        await freqtrade_service.stop_instance(orchestrator, str(bot.container_ref))
    except FreqtradeUnavailableError as exc:
        logger.error(f"guardian 日亏熔断停机失败 bot={bot.id}: {exc}")
        return
    bot.status = BotStatusEnum.STOPPED
    db.add(
        _risk_event(
            bot,
            level=RiskEventLevelEnum.DANGER,
            title="日亏限制触发，已强制停机",
            description=f"当日收益 {pnl_pct:.2f}% 跌破限制 -{abs(limit) * 100:g}%",
            action="强制停止实例",
        )
    )
    logger.warning(f"guardian 日亏熔断：bot={bot.id} pnl={pnl_pct:.2f}% 已强制停机")


async def _reconcile_once() -> None:
    from libs.ctrl.db.sqlalchemy import new_async_session

    async with new_async_session() as db:
        orchestrator = freqtrade_service.resolve_orchestrator_config(
            await get_engine_connection_config(db, EngineKindEnum.FREQTRADE)
        )
        if not orchestrator.ready:
            return
        bots = (
            await db.scalars(select(Bot).where(Bot.status == BotStatusEnum.RUNNING))
        ).all()
        for bot in bots:
            if not bot.container_ref:
                continue
            try:
                instance = await freqtrade_service.get_instance(orchestrator, bot.container_ref)
            except FreqtradeUnavailableError:
                return  # 编排器不可达：本轮放弃，避免误判全部实例丢失。
            if instance is None or instance.status != "running":
                bot.status = BotStatusEnum.STOPPED
                db.add(
                    _risk_event(
                        bot,
                        level=RiskEventLevelEnum.WARN,
                        title="实例状态对账：容器已停止",
                        description=f"容器 {bot.container_ref} 实际状态为 "
                        f"{'缺失' if instance is None else instance.status}，已同步为停止",
                        action=None,
                    )
                )
                continue
            await _check_daily_loss(db, orchestrator, bot)
        await db.commit()


async def _loop() -> None:
    while True:
        try:
            await _reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"guardian 轮询异常: {exc}")
        await asyncio.sleep(_GUARD_INTERVAL_SECONDS)


def start_guardian() -> None:
    """在 lifespan 启动守护任务（幂等）。"""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop_guardian() -> None:
    """在 lifespan 关闭时取消守护任务。"""
    global _task
    if _task is not None:
        _task.cancel()
        with suppress(asyncio.CancelledError):
            await _task
        _task = None
