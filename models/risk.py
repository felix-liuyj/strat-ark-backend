"""风控规则与风控事件 ORM 模型及枚举。

覆盖多层风控（账户 / Bot / 策略 / 交易对 / 订单 / AI 信号级）与多类规则
（每日亏损上限 / 最大回撤 / 最大仓位 / 最大杠杆 / 连亏冷却 / 新闻 / 波动率 / 流动性），
以及风控触发记录（risk_events）。绑定关系不用 ORM relationship，跨模块用字符串外键。
"""

from enum import StrEnum

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "RiskEvent",
    "RiskEventLevelEnum",
    "RiskRule",
    "RiskRuleScopeEnum",
    "RiskRuleTypeEnum",
)


class RiskRuleScopeEnum(StrEnum):
    """风控分层（与前端 6 张分层卡对齐）。"""

    ACCOUNT = "account"
    BOT = "bot"
    STRATEGY = "strategy"
    SYMBOL = "symbol"
    ORDER = "order"
    SIGNAL = "signal"


class RiskRuleTypeEnum(StrEnum):
    """风控规则类型（与前端 RULES 列表对齐）。"""

    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_DRAWDOWN = "max_drawdown"
    MAX_POSITION_SIZE = "max_position_size"
    MAX_LEVERAGE = "max_leverage"
    COOLDOWN = "cooldown"
    NEWS_FILTER = "news_filter"
    VOLATILITY_FILTER = "volatility_filter"
    LIQUIDITY_FILTER = "liquidity_filter"


class RiskEventLevelEnum(StrEnum):
    """风控事件级别（驱动前端事件点颜色与告警优先级）。"""

    INFO = "info"
    WARN = "warn"
    DANGER = "danger"
    SUCCESS = "success"


class RiskRule(Base, TimestampMixin):
    """单条风控规则（某一分层下某一类型的阈值配置）。"""

    __tablename__ = "risk_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    scope: Mapped[RiskRuleScopeEnum] = mapped_column(String(20), nullable=False, index=True)
    rule_type: Mapped[RiskRuleTypeEnum] = mapped_column(String(40), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # 数值类规则的当前值与限额值（阈值类）；开关类规则用 enabled 表达，数值留空。
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    limit_value: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 可选绑定到具体 Bot / 策略 / 交易对（字符串外键或符号，散落分层下生效目标）。
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bots.id"), nullable=True, default=None)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), nullable=True, default=None)
    symbol: Mapped[str | None] = mapped_column(String(40), nullable=True, default=None)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RiskEvent(Base, TimestampMixin):
    """风控触发记录（触发记录列表 / 告警源）。"""

    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    level: Mapped[RiskEventLevelEnum] = mapped_column(String(20), nullable=False, index=True)
    scope: Mapped[RiskRuleScopeEnum] = mapped_column(String(20), nullable=False, default=RiskRuleScopeEnum.ACCOUNT)
    rule_type: Mapped[RiskRuleTypeEnum | None] = mapped_column(String(40), nullable=True, default=None)
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    symbol: Mapped[str | None] = mapped_column(String(40), nullable=True, default=None)
    # 关联的规则 / Bot / 策略（字符串外键，不建 relationship）。
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("risk_rules.id"), nullable=True, default=None)
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bots.id"), nullable=True, default=None)
    # 是否已采取拦截 / 处置动作（拦截订单、停止策略等）。
    action_taken: Mapped[str | None] = mapped_column(String(120), nullable=True, default=None)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
