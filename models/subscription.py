"""订阅域 ORM 模型与枚举：套餐定义 / 订阅记录 / 本月用量 / 账单发票。

与前端 ``strat-ark-frontend/src/subscription/plans.ts`` 数据形状对齐；
套餐升级 / 降级 / 取消仅更新本地订阅记录与 ``users.plan``，绝不接入真实支付。
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin
from models.account import PlanEnum

__all__ = (
    "BillingCycleEnum",
    "Invoice",
    "InvoiceStatusEnum",
    "Plan",
    "Subscription",
    "SubscriptionStatusEnum",
    "UsageCounter",
    "UsageMetricEnum",
)


class BillingCycleEnum(StrEnum):
    """计费周期（前端月 / 年切换）。"""

    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatusEnum(StrEnum):
    """订阅状态。"""

    ACTIVE = "active"
    CANCELED = "canceled"
    EXPIRED = "expired"


class InvoiceStatusEnum(StrEnum):
    """发票 / 账单状态。"""

    PAID = "paid"
    PENDING = "pending"
    REFUNDED = "refunded"


class UsageMetricEnum(StrEnum):
    """用量计数维度（与套餐额度上限一一对应）。"""

    BOTS = "bots"
    STRATEGIES = "strategies"
    AI_ANALYSIS = "ai_analysis"
    BACKTESTS = "backtests"


class Plan(Base, TimestampMixin):
    """套餐定义（free / pro / team）。

    全平台共享的目录数据，不归属单个用户；额度上限以 ``-1`` 表示无限制。
    价格、特性、额度均与前端 ``PLANS`` 常量对齐；展示文案字段存稳定 i18n key。
    """

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[PlanEnum] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    tagline: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    price_monthly: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    # 年付折合每月价（前端按 10 个月计，省 2 个月）。
    price_yearly_per_month: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    highlight: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 特性条目 i18n key 列表，交由前端按当前语言渲染。
    features: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # 额度上限：bots / strategies / ai_analysis / backtests，-1 表示无限制。
    limit_bots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_strategies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_ai_analysis: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_backtests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Subscription(Base, TimestampMixin):
    """用户订阅记录。

    每次切换套餐写入一条新记录并把旧记录置为 ``canceled``；当前生效订阅 =
    最新一条 ``active`` 记录。免费版直接标记已支付（金额 0）。
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_code: Mapped[PlanEnum] = mapped_column(String(20), nullable=False, default=PlanEnum.FREE)
    billing_cycle: Mapped[BillingCycleEnum] = mapped_column(
        String(20), nullable=False, default=BillingCycleEnum.MONTHLY
    )
    status: Mapped[SubscriptionStatusEnum] = mapped_column(
        String(20), nullable=False, default=SubscriptionStatusEnum.ACTIVE, index=True
    )
    # 周期内单价快照（下单时锁定，避免套餐改价影响历史）。
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stripe 订阅 ID（接 Stripe 时由 Webhook 回填；mock 流程为空）。
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None, index=True)


class UsageCounter(Base, TimestampMixin):
    """本月用量计数（按 用户 + 维度 + 账期月 唯一）。

    ``period`` 形如 ``2026-06``；展示时与套餐额度上限组合成用量条占比。
    """

    __tablename__ = "usage_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric: Mapped[UsageMetricEnum] = mapped_column(String(30), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False, default="", index=True)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Invoice(Base, TimestampMixin):
    """账单 / 发票记录（模拟，无真实支付）。

    切换到付费套餐时生成一条 ``paid`` 发票；发票下载由 service stub 产出。
    """

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True)
    # 发票号（对外展示，形如 INV-202606-0001）。
    invoice_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    plan_code: Mapped[PlanEnum] = mapped_column(String(20), nullable=False, default=PlanEnum.FREE)
    item: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    status: Mapped[InvoiceStatusEnum] = mapped_column(
        String(20), nullable=False, default=InvoiceStatusEnum.PAID
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stripe 托管发票 PDF / 详情链接（接 Stripe 时由 Webhook 回填；下载时优先返回此链接）。
    external_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
