"""策略 ORM 模型与枚举（strategies + strategy_versions 两表）。

对齐前端 Strategy Lab：策略类型 / 周期 / 风险标签 / 回测指标 / 参数 / 版本记录 / 源码。
参数以 JSON 存储（有序键值对列表），版本为独立表 strategy_versions。
"""

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "Strategy",
    "StrategyRiskEnum",
    "StrategyStatusEnum",
    "StrategyTypeEnum",
    "StrategyVersion",
)


class StrategyTypeEnum(StrEnum):
    """策略类型（前端：趋势跟踪 / 均值回归 / 突破 / AI 辅助 / 风控策略）。"""

    TREND = "trend"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    AI_ASSISTED = "ai_assisted"
    RISK_GUARD = "risk_guard"


class StrategyRiskEnum(StrEnum):
    """策略风险等级（前端：高 / 中 / 低）。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StrategyStatusEnum(StrEnum):
    """策略状态（前端：可用 / 测试中）。"""

    AVAILABLE = "available"
    TESTING = "testing"


class Strategy(Base, TimestampMixin):
    """单个策略（系统内置或用户导入/新建）。

    user_id 为空表示平台内置策略，对所有用户可见；非空表示用户私有策略。
    """

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True, default=None
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    strategy_type: Mapped[StrategyTypeEnum] = mapped_column(String(30), nullable=False)
    icon: Mapped[str] = mapped_column(String(30), nullable=False, default="trend")
    icon_color: Mapped[str] = mapped_column(String(30), nullable=False, default="ico-brand")
    timeframe: Mapped[str] = mapped_column(String(40), nullable=False, default="15m")
    market: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    risk: Mapped[StrategyRiskEnum] = mapped_column(String(20), nullable=False, default=StrategyRiskEnum.MEDIUM)
    status: Mapped[StrategyStatusEnum] = mapped_column(
        String(20), nullable=False, default=StrategyStatusEnum.AVAILABLE
    )
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 回测指标（展示用文案，回测真实计算属 backtests 域）。
    backtest_return: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    max_drawdown: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    win_rate: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    sharpe: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    equity_curve: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 有序参数键值对：[["EMA Fast", "21"], ...]。
    params: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False, default=list)
    # 风险标签：["趋势", "中风险", "15m/1h"]。
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class StrategyVersion(Base, TimestampMixin):
    """策略版本记录（前端版本时间线 v1.3 current / v1.2 / v1.1）。"""

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1.0")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    changelog: Mapped[str] = mapped_column(Text, nullable=False, default="")
    params_snapshot: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False, default=list)
    metrics_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
