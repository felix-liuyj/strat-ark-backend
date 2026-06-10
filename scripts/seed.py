"""数据库初始化 + 内置策略种子（幂等）。

用法（已激活 venv / poetry 环境）::

    python -m scripts.seed

执行内容：
1. ``init_db()`` 建表（多 worker 安全，幂等）。
2. 写入平台内置策略（``user_id IS NULL`` + ``is_builtin=True``），供 Strategy Lab 列表。

幂等：按策略名判重，已存在则跳过；可重复运行。
账号一律走注册流程创建（管理员邮箱白名单自动判定角色），不再写演示账号。
套餐目录、引擎默认配置等由对应 ViewModel 首次访问时惰性 seed，无需在此处理。
"""

import asyncio

from sqlalchemy import select

from libs.ctrl.db.sqlalchemy import init_db, new_async_session
from models.strategy import Strategy, StrategyRiskEnum, StrategyStatusEnum, StrategyTypeEnum

BUILTIN_STRATEGIES: list[dict] = [
    {
        "name": "Trend EMA RSI V1",
        "freqtrade_class": "TrendEmaRsiV1",
        "strategy_type": StrategyTypeEnum.TREND,
        "icon": "trend",
        "icon_color": "ico-brand",
        "timeframe": "15m / 1h",
        "market": "strategy.marketTrend",
        "risk": StrategyRiskEnum.MEDIUM,
        "status": StrategyStatusEnum.AVAILABLE,
        "backtest_return": "+18.4%",
        "max_drawdown": "-7.2%",
        "win_rate": "57%",
        "sharpe": "1.84",
        "params": [["EMA Fast", "21"], ["EMA Slow", "55"], ["RSI Period", "14"], ["RSI Threshold", "52"]],
        "tags": ["strategy.catTrend", "EMA", "RSI"],
        "description": "strategy.desc.trend",
    },
    {
        "name": "Mean Reversion BB",
        "freqtrade_class": "MeanReversionBB",
        "strategy_type": StrategyTypeEnum.MEAN_REVERSION,
        "icon": "range",
        "icon_color": "ico-blue",
        "timeframe": "5m / 15m",
        "market": "strategy.marketRange",
        "risk": StrategyRiskEnum.MEDIUM,
        "status": StrategyStatusEnum.AVAILABLE,
        "backtest_return": "+11.2%",
        "max_drawdown": "-5.1%",
        "win_rate": "61%",
        "sharpe": "1.52",
        "params": [["BB Period", "20"], ["BB Std", "2.0"], ["RSI Period", "14"]],
        "tags": ["strategy.catRange", "Bollinger", "strategy.typeMeanRev"],
        "description": "strategy.desc.meanRev",
    },
    {
        "name": "Donchian Breakout",
        "freqtrade_class": "DonchianBreakout",
        "strategy_type": StrategyTypeEnum.BREAKOUT,
        "icon": "breakout",
        "icon_color": "ico-green",
        "timeframe": "1h / 4h",
        "market": "strategy.marketBreakout",
        "risk": StrategyRiskEnum.HIGH,
        "status": StrategyStatusEnum.TESTING,
        "backtest_return": "+24.6%",
        "max_drawdown": "-12.3%",
        "win_rate": "48%",
        "sharpe": "1.36",
        "params": [["Channel", "20"], ["ATR Period", "14"], ["ATR Mult", "1.5"]],
        "tags": ["strategy.catBreakout", "Donchian", "ATR"],
        "description": "strategy.desc.breakout",
    },
    {
        "name": "Risk Guard Overlay",
        "freqtrade_class": "RiskGuardOverlay",
        "strategy_type": StrategyTypeEnum.RISK_GUARD,
        "icon": "shield",
        "icon_color": "ico-amber",
        "timeframe": "strategy.tfAll",
        "market": "strategy.marketGuard",
        "risk": StrategyRiskEnum.LOW,
        "status": StrategyStatusEnum.AVAILABLE,
        "backtest_return": "—",
        "max_drawdown": "—",
        "win_rate": "—",
        "sharpe": "—",
        "params": [["Max DD", "10%"], ["Daily Loss", "3%"], ["Vol Filter", "on"]],
        "tags": ["strategy.catRisk", "Drawdown", "Volatility"],
        "description": "strategy.desc.riskGuard",
    },
]


async def seed_strategies(db) -> int:
    created = 0
    for spec in BUILTIN_STRATEGIES:
        exists = await db.scalar(
            select(Strategy).where(Strategy.name == spec["name"], Strategy.is_builtin.is_(True))
        )
        if exists is not None:
            # 存量行补填 freqtrade 类名映射（早期种子无此字段）。
            if not exists.freqtrade_class and spec.get("freqtrade_class"):
                exists.freqtrade_class = spec["freqtrade_class"]
            continue
        db.add(Strategy(user_id=None, is_builtin=True, **spec))
        created += 1
    return created


async def main() -> None:
    await init_db()
    async with new_async_session() as db:
        strategies = await seed_strategies(db)
        await db.commit()
    print(f"seed 完成：新增内置策略 {strategies} 个")


if __name__ == "__main__":
    asyncio.run(main())
