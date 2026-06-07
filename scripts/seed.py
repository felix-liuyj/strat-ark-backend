"""数据库初始化 + 演示种子数据（幂等）。

用法（已激活 venv / poetry 环境）::

    python -m scripts.seed

执行内容：
1. ``init_db()`` 建表（多 worker 安全，幂等）。
2. 写入三角色演示账号（管理员 / 普通用户 / 订阅用户），与前端 mock 账号对齐。
3. 写入平台内置策略（``user_id IS NULL`` + ``is_builtin=True``），供 Strategy Lab 列表。

幂等：按邮箱 / 策略名判重，已存在则跳过；可重复运行。
套餐目录、引擎默认配置等由对应 ViewModel 首次访问时惰性 seed，无需在此处理。
"""

import asyncio

from sqlalchemy import select

from libs.ctrl.db.sqlalchemy import init_db, new_async_session
from models.account import PlanEnum, UserTypeEnum
from models.strategy import Strategy, StrategyRiskEnum, StrategyStatusEnum, StrategyTypeEnum
from models.user import User

DEMO_PASSWORD = "strategy123"

DEMO_USERS: list[dict] = [
    {"email": "alex@stratark.io", "display_name": "Alex Chen", "user_type": UserTypeEnum.ADMIN, "plan": PlanEnum.PRO},
    {"email": "wei@stratark.io", "display_name": "Wei Zhang", "user_type": UserTypeEnum.CLIENT, "plan": PlanEnum.FREE},
    {"email": "lin@stratark.io", "display_name": "Lin Yu", "user_type": UserTypeEnum.CLIENT, "plan": PlanEnum.PRO},
]

BUILTIN_STRATEGIES: list[dict] = [
    {
        "name": "Trend EMA RSI V1",
        "strategy_type": StrategyTypeEnum.TREND,
        "icon": "trend",
        "icon_color": "ico-brand",
        "timeframe": "15m / 1h",
        "market": "单边趋势行情",
        "risk": StrategyRiskEnum.MEDIUM,
        "status": StrategyStatusEnum.AVAILABLE,
        "backtest_return": "+18.4%",
        "max_drawdown": "-7.2%",
        "win_rate": "57%",
        "sharpe": "1.84",
        "params": [["EMA Fast", "21"], ["EMA Slow", "55"], ["RSI Period", "14"], ["RSI Threshold", "52"]],
        "tags": ["趋势", "EMA", "RSI"],
        "description": "均线趋势 + RSI 过滤的趋势跟踪策略，适合单边行情。",
    },
    {
        "name": "Mean Reversion BB",
        "strategy_type": StrategyTypeEnum.MEAN_REVERSION,
        "icon": "range",
        "icon_color": "ico-blue",
        "timeframe": "5m / 15m",
        "market": "震荡区间",
        "risk": StrategyRiskEnum.MEDIUM,
        "status": StrategyStatusEnum.AVAILABLE,
        "backtest_return": "+11.2%",
        "max_drawdown": "-5.1%",
        "win_rate": "61%",
        "sharpe": "1.52",
        "params": [["BB Period", "20"], ["BB Std", "2.0"], ["RSI Period", "14"]],
        "tags": ["震荡", "布林带", "均值回归"],
        "description": "布林带均值回归策略，区间震荡行情捕捉超买超卖。",
    },
    {
        "name": "Donchian Breakout",
        "strategy_type": StrategyTypeEnum.BREAKOUT,
        "icon": "breakout",
        "icon_color": "ico-green",
        "timeframe": "1h / 4h",
        "market": "趋势启动 / 突破",
        "risk": StrategyRiskEnum.HIGH,
        "status": StrategyStatusEnum.TESTING,
        "backtest_return": "+24.6%",
        "max_drawdown": "-12.3%",
        "win_rate": "48%",
        "sharpe": "1.36",
        "params": [["Channel", "20"], ["ATR Period", "14"], ["ATR Mult", "1.5"]],
        "tags": ["突破", "唐奇安通道", "波动"],
        "description": "唐奇安通道突破策略，捕捉趋势启动，止损用 ATR。",
    },
    {
        "name": "Risk Guard Overlay",
        "strategy_type": StrategyTypeEnum.RISK_GUARD,
        "icon": "shield",
        "icon_color": "ico-amber",
        "timeframe": "全周期",
        "market": "全行情（风控叠加）",
        "risk": StrategyRiskEnum.LOW,
        "status": StrategyStatusEnum.AVAILABLE,
        "backtest_return": "—",
        "max_drawdown": "—",
        "win_rate": "—",
        "sharpe": "—",
        "params": [["Max DD", "10%"], ["Daily Loss", "3%"], ["Vol Filter", "on"]],
        "tags": ["风控", "回撤", "波动率"],
        "description": "风控叠加策略：回撤 / 日亏 / 波动率过滤，与其它策略组合使用。",
    },
]


async def seed_users(db) -> int:
    created = 0
    for spec in DEMO_USERS:
        exists = await db.scalar(select(User).where(User.email == spec["email"]))
        if exists is not None:
            continue
        user = User(
            email=spec["email"],
            display_name=spec["display_name"],
            user_type=spec["user_type"],
            plan=spec["plan"],
            is_active=True,
            is_verified=True,
        )
        user.set_password(DEMO_PASSWORD)
        db.add(user)
        created += 1
    return created


async def seed_strategies(db) -> int:
    created = 0
    for spec in BUILTIN_STRATEGIES:
        exists = await db.scalar(
            select(Strategy).where(Strategy.name == spec["name"], Strategy.is_builtin.is_(True))
        )
        if exists is not None:
            continue
        db.add(Strategy(user_id=None, is_builtin=True, **spec))
        created += 1
    return created


async def main() -> None:
    await init_db()
    async with new_async_session() as db:
        users = await seed_users(db)
        strategies = await seed_strategies(db)
        await db.commit()
    print(f"seed 完成：新增用户 {users} 个，内置策略 {strategies} 个（演示密码：{DEMO_PASSWORD}）")


if __name__ == "__main__":
    asyncio.run(main())
