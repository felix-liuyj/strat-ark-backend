"""回测任务 ORM 模型与枚举（回测中心）。"""

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "BacktestStatusEnum",
    "BacktestTask",
)


class BacktestStatusEnum(StrEnum):
    """回测任务状态（与前端任务列表徽标对齐）。"""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BacktestTask(Base, TimestampMixin):
    """回测任务及其结果快照。

    结果指标与各序列（权益曲线 / 回撤 / 每日收益 / 交易对归因）以 JSON 整体落库，
    避免为一次性回测产物建多张明细表；策略引用用 strategy_id 字符串外键（跨模块）。
    """

    __tablename__ = "backtest_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), nullable=True, index=True)
    strategy_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    symbol: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, default="1h")
    start_date: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    end_date: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    initial_balance: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)
    fee_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0004)
    slippage_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0005)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=BacktestStatusEnum.QUEUED, index=True)

    # 绩效指标快照（任务完成后回填）。
    total_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    cagr: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    best_pair: Mapped[str | None] = mapped_column(String(40), nullable=True)
    worst_pair: Mapped[str | None] = mapped_column(String(40), nullable=True)
    final_balance: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 各序列与 AI 复盘以 JSON 整体存储。
    result_series: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ai_review: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
