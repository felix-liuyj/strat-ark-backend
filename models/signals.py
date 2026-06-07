"""交易信号 ORM 模型与枚举（信号中心）。"""

from enum import StrEnum

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "Signal",
    "SignalDirectionEnum",
    "SignalRiskLevelEnum",
    "SignalSourceEnum",
    "SignalStatusEnum",
)


class SignalDirectionEnum(StrEnum):
    """信号方向（与前端 Long / Short / Neutral 对齐）。"""

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class SignalSourceEnum(StrEnum):
    """信号来源（与前端来源筛选对齐）。"""

    AI = "ai"
    STRATEGY = "strategy"
    AI_STRATEGY = "ai_strategy"
    WEBHOOK = "webhook"
    MANUAL = "manual"


class SignalRiskLevelEnum(StrEnum):
    """信号风险等级（与前端 Low / Med / High 对齐）。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalStatusEnum(StrEnum):
    """信号状态机：Generated → Reviewed → Approved → Executed；可转 Rejected / Expired。"""

    GENERATED = "generated"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    EXECUTED = "executed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Signal(Base, TimestampMixin):
    """交易信号（AI / 策略 / 外部 webhook / 手动来源），含入场/止损/止盈与状态机。

    AI 仅产出辅助决策信号，approve / execute 是人工与风控动作；批准不等于自动下单。
    """

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default=SignalDirectionEnum.LONG)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default=SignalSourceEnum.STRATEGY)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default=SignalRiskLevelEnum.MEDIUM)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SignalStatusEnum.GENERATED, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
