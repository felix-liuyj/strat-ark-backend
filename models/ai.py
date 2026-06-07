"""AI 投研报告 ORM 模型与枚举（agent_reports，多智能体投研）。"""

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "AgentReport",
    "AgentReportTypeEnum",
)


class AgentReportTypeEnum(StrEnum):
    """报告类型：市场分析 / 信号复核 / 回测复盘。"""

    MARKET_ANALYSIS = "market_analysis"
    SIGNAL_REVIEW = "signal_review"
    BACKTEST_REVIEW = "backtest_review"


class AgentReport(Base, TimestampMixin):
    """TradingAgents 多智能体协作产出的结构化投研报告。

    八类 Agent（Market / Technical / Sentiment / Bull / Bear / Trader / Risk /
    Portfolio）的观点与结构化结论以 JSON 整体落库；市场分析类的关键结构化字段
    （信号 / 置信度 / 入场区间 / 止损 / 止盈 / 风险）单列冗余，便于列表与筛选。
    AI 仅产出辅助决策结论，不直接下单。
    """

    __tablename__ = "agent_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    report_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default=AgentReportTypeEnum.MARKET_ANALYSIS, index=True
    )
    symbol: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, default="1h")

    # 市场分析结构化结论（其它报告类型可留空）。
    market_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    signal: Mapped[str | None] = mapped_column(String(24), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 入场区间 / 止损 / 止盈 / 多空分值 / 八类 Agent 观点等整体存 JSON。
    structured: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    agents: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)

    # 关联对象（信号复核关联 signal、回测复盘关联 backtest_task），跨模块字符串外键。
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True, index=True)
    backtest_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("backtest_tasks.id"), nullable=True, index=True
    )
