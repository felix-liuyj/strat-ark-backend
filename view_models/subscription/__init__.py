"""订阅域 ViewModel：套餐目录 / 当前订阅 / 用量 / 账单 / Stripe Checkout / 客户门户 / Webhook / 后台套餐管理。

升级走 Stripe 订阅 Checkout，取消 / 管理走 Customer Portal，订阅激活与发票以 Stripe Webhook 为准；
后台可编辑套餐元数据（落库 plans 表）并「同步到 Stripe」（创建 Product + Price 并回填价格 ID）。
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from configs import get_settings
from forms.subscription import ChangePlanForm, PlanUpdateForm
from libs.auth.permissions import PermissionChecker
from libs.integrations import billing
from libs.logger import logger
from libs.sso import AUTH_INVALID_MESSAGE
from models.account import PlanEnum, UserTypeEnum
from models.ai import AgentReport
from models.audit_log import ActorTypeEnum, AuditActionEnum, AuditCategoryEnum
from models.backtests import BacktestTask
from models.bot import Bot
from models.strategy import Strategy
from models.subscription import (
    BillingCycleEnum,
    Invoice,
    InvoiceStatusEnum,
    Plan,
    Subscription,
    SubscriptionStatusEnum,
    UsageMetricEnum,
)
from models.user import User
from responses.subscription import (
    CheckoutResponseData,
    CurrentSubscriptionResponseData,
    InvoiceDownloadResponseData,
    InvoiceResponseData,
    PlanLimitsResponseData,
    PlanResponseData,
    PortalResponseData,
    UsageBarResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = (
    "CancelSubscriptionViewModel",
    "ChangePlanViewModel",
    "CreateCheckoutViewModel",
    "CreatePortalViewModel",
    "DownloadInvoiceViewModel",
    "GetCurrentSubscriptionViewModel",
    "ListInvoicesViewModel",
    "ListPlansViewModel",
    "ListUsageViewModel",
    "StripeWebhookViewModel",
    "SyncPlanToStripeViewModel",
    "UpdatePlanViewModel",
)

# 套餐顺序：用于判定升级 / 降级方向（与前端 PLAN_ORDER 对齐）。
_PLAN_ORDER: dict[PlanEnum, int] = {PlanEnum.FREE: 0, PlanEnum.PRO: 1, PlanEnum.TEAM: 2}

# 套餐目录种子（与前端 PLANS 常量 1:1 对齐；展示文案一律存 i18n key，-1 表示无限制）。
_PLAN_SEED: list[dict] = [
    {
        "code": PlanEnum.FREE,
        "name": "subscription.plan.free",
        "tagline": "subscription.tagline.free",
        "price_monthly": 0,
        "price_yearly_per_month": 0,
        "highlight": False,
        "features": [
            "subscription.feat.free.bots",
            "subscription.feat.free.strategies",
            "subscription.feat.free.ai",
            "subscription.feat.free.dryrun",
        ],
        "limit_bots": 1,
        "limit_strategies": 3,
        "limit_ai_analysis": 20,
        "limit_backtests": 10,
        "sort_order": 0,
    },
    {
        "code": PlanEnum.PRO,
        "name": "subscription.plan.pro",
        "tagline": "subscription.tagline.pro",
        "price_monthly": 49,
        "price_yearly_per_month": 41,
        "highlight": True,
        "features": [
            "subscription.feat.pro.bots",
            "subscription.feat.pro.strategies",
            "subscription.feat.pro.ai",
            "subscription.feat.pro.live",
        ],
        "limit_bots": 10,
        "limit_strategies": 20,
        "limit_ai_analysis": 300,
        "limit_backtests": -1,
        "sort_order": 1,
    },
    {
        "code": PlanEnum.TEAM,
        "name": "subscription.plan.team",
        "tagline": "subscription.tagline.team",
        "price_monthly": 149,
        "price_yearly_per_month": 124,
        "highlight": False,
        "features": [
            "subscription.feat.team.bots",
            "subscription.feat.team.strategies",
            "subscription.feat.team.ai",
            "subscription.feat.team.live",
        ],
        "limit_bots": -1,
        "limit_strategies": -1,
        "limit_ai_analysis": 2000,
        "limit_backtests": -1,
        "sort_order": 2,
    },
]

# 用量维度展示标签 i18n key。
_USAGE_LABELS: dict[UsageMetricEnum, str] = {
    UsageMetricEnum.BOTS: "subscription.usage.bots",
    UsageMetricEnum.STRATEGIES: "subscription.usage.strategies",
    UsageMetricEnum.AI_ANALYSIS: "subscription.usage.ai",
    UsageMetricEnum.BACKTESTS: "subscription.usage.backtests",
}


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _metric_limit(plan: Plan, metric: UsageMetricEnum) -> int:
    mapping = {
        UsageMetricEnum.BOTS: plan.limit_bots,
        UsageMetricEnum.STRATEGIES: plan.limit_strategies,
        UsageMetricEnum.AI_ANALYSIS: plan.limit_ai_analysis,
        UsageMetricEnum.BACKTESTS: plan.limit_backtests,
    }
    return mapping[metric]


def _build_plan_response(plan: Plan) -> PlanResponseData:
    # 注意：Stripe 产品 / 价格 ID 属于内部对接信息，不随响应外泄（/plans 公开可读）。
    return PlanResponseData(
        id=plan.code,
        name=plan.name,
        tagline=plan.tagline,
        priceMonthly=float(plan.price_monthly),
        priceYearlyPerMonth=float(plan.price_yearly_per_month),
        highlight=plan.highlight,
        features=list(plan.features or []),
        limits=PlanLimitsResponseData(
            bots=plan.limit_bots,
            strategies=plan.limit_strategies,
            aiAnalysis=plan.limit_ai_analysis,
            backtests=plan.limit_backtests,
        ),
    )


def _build_current_subscription(
    plan_code: PlanEnum, sub: Subscription | None, *, fallback_unit_price: float = 0.0
) -> CurrentSubscriptionResponseData:
    """从 users.plan + 最新 active 订阅记录构造当前订阅概况（含 stripeEnabled 开关）。"""
    return CurrentSubscriptionResponseData(
        planCode=plan_code,
        status=sub.status if sub else SubscriptionStatusEnum.ACTIVE,
        billingCycle=sub.billing_cycle if sub else BillingCycleEnum.MONTHLY,
        unitPrice=float(sub.unit_price) if sub else fallback_unit_price,
        startedAt=_iso_or_none(sub.started_at) if sub else None,
        currentPeriodEnd=_iso_or_none(sub.current_period_end) if sub else None,
        canceledAt=_iso_or_none(sub.canceled_at) if sub else None,
        stripeEnabled=billing.stripe_enabled(),
    )


async def _ensure_plans_seeded(db: AsyncSession) -> list[Plan]:
    """惰性种入套餐目录：仅当 plans 表为空时写入种子，幂等。"""
    plans = list((await db.scalars(select(Plan).order_by(Plan.sort_order.asc()))).all())
    if plans:
        return plans
    for seed in _PLAN_SEED:
        db.add(Plan(**seed))
    await db.commit()
    return list((await db.scalars(select(Plan).order_by(Plan.sort_order.asc()))).all())


async def _get_plan(db: AsyncSession, code: PlanEnum) -> Plan | None:
    plans = await _ensure_plans_seeded(db)
    return next((p for p in plans if p.code == code), None)


async def _count_rows(db: AsyncSession, model: object, *where: object) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def _load_actual_usage(db: AsyncSession, user_id: int) -> dict[UsageMetricEnum, int]:
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {
        UsageMetricEnum.BOTS: await _count_rows(db, Bot, Bot.user_id == user_id),
        UsageMetricEnum.STRATEGIES: await _count_rows(db, Strategy, Strategy.user_id == user_id),
        UsageMetricEnum.AI_ANALYSIS: await _count_rows(
            db, AgentReport, AgentReport.user_id == user_id, AgentReport.created_at >= month_start
        ),
        UsageMetricEnum.BACKTESTS: await _count_rows(
            db, BacktestTask, BacktestTask.user_id == user_id, BacktestTask.created_at >= month_start
        ),
    }


async def _apply_subscription_change(
    db: AsyncSession,
    user: User,
    plan: Plan,
    cycle: BillingCycleEnum,
    *,
    stripe_subscription_id: str | None = None,
    write_invoice: bool = True,
) -> Subscription:
    """本地应用套餐变更：撤销旧 active 订阅 → 写新 active 订阅(+可选已支付发票) → 更新 users.plan。

    用于 Stripe Webhook 激活订阅；发票由 invoice.paid 事件单独落地、带托管 PDF 链接。
    """
    now = datetime.now(UTC)
    actives = (
        await db.scalars(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.status == SubscriptionStatusEnum.ACTIVE,
            )
        )
    ).all()
    for sub in actives:
        sub.status = SubscriptionStatusEnum.CANCELED
        sub.canceled_at = now
    unit_price = float(plan.price_yearly_per_month) if cycle == BillingCycleEnum.YEARLY else float(plan.price_monthly)
    period_days = 365 if cycle == BillingCycleEnum.YEARLY else 30
    subscription = Subscription(
        user_id=user.id,
        plan_code=plan.code,
        billing_cycle=cycle,
        status=SubscriptionStatusEnum.ACTIVE,
        unit_price=unit_price,
        started_at=now,
        current_period_end=now + timedelta(days=period_days),
        stripe_subscription_id=stripe_subscription_id,
    )
    db.add(subscription)
    await db.flush()
    if write_invoice:
        invoice_no = f"INV-{now.strftime('%Y%m')}-{now.strftime('%d%H%M%S')}"
        db.add(
            Invoice(
                user_id=user.id,
                subscription_id=subscription.id,
                invoice_no=invoice_no,
                plan_code=plan.code,
                item="subscription.invoice.subscription",
                amount=unit_price,
                currency="USD",
                status=InvoiceStatusEnum.PAID,
                issued_at=now,
            )
        )
    user.plan = plan.code
    await db.commit()
    await db.refresh(subscription)
    return subscription


class ListPlansViewModel(BaseViewModel):
    """套餐目录（free / pro / team），公开可读，无需登录。"""

    def __init__(self, request: Request, db: AsyncSession) -> None:
        super().__init__(request=request)
        self.db = db

    async def before(self) -> None:
        await super().before()
        plans = await _ensure_plans_seeded(self.db)
        self.operating_successfully([_build_plan_response(p) for p in plans])


class GetCurrentSubscriptionViewModel(BaseViewModel):
    """当前订阅概况（基于 users.plan + 最新 active 订阅记录）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        sub = await self.db.scalar(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status == SubscriptionStatusEnum.ACTIVE,
            )
            .order_by(Subscription.id.desc())
            .limit(1)
        )

        plan = await _get_plan(self.db, user.plan)
        unit_price = float(plan.price_monthly) if plan else 0.0
        self.operating_successfully(
            _build_current_subscription(user.plan, sub, fallback_unit_price=unit_price)
        )


class ListUsageViewModel(BaseViewModel):
    """本月用量条（按当前套餐额度上限给出占比）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        plan = await _get_plan(self.db, user.plan)
        if plan is None:
            self.not_found("套餐不存在")
            return

        counters = await _load_actual_usage(self.db, user.id)
        bars = [self._build_bar(plan, metric, counters.get(metric, 0)) for metric in UsageMetricEnum]
        self.operating_successfully(bars)

    @staticmethod
    def _build_bar(plan: Plan, metric: UsageMetricEnum, used: int) -> UsageBarResponseData:
        limit = _metric_limit(plan, metric)
        if limit < 0:
            value = "subscription.usageValue.unlimited"
            width = "100%"
        else:
            pct = 0 if limit == 0 else min(100, round(used / limit * 100))
            value = f"{used} / {limit}"
            width = f"{pct}%"
        return UsageBarResponseData(
            metric=metric,
            label=_USAGE_LABELS[metric],
            used=used,
            limit=limit,
            value=value,
            width=width,
        )


class ListInvoicesViewModel(BaseViewModel):
    """账单 / 发票历史（按时间倒序）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        invoices = (
            await self.db.scalars(
                select(Invoice)
                .where(Invoice.user_id == int(self.checker.user_id))
                .order_by(Invoice.id.desc())
            )
        ).all()
        self.operating_successfully([self._build_invoice(i) for i in invoices])

    @staticmethod
    def _build_invoice(invoice: Invoice) -> InvoiceResponseData:
        return InvoiceResponseData(
            id=invoice.id,
            invoiceNo=invoice.invoice_no,
            planCode=invoice.plan_code,
            item=invoice.item,
            amount=float(invoice.amount),
            currency=invoice.currency,
            status=invoice.status,
            issuedAt=_iso_or_none(invoice.issued_at),
        )


class DownloadInvoiceViewModel(BaseViewModel):
    """发票下载：返回 Stripe 托管发票 PDF 链接（前端新开窗口打开）。"""

    audit_action = AuditActionEnum.EXPORT
    audit_resource = "invoice"
    audit_enabled = True

    def __init__(
        self, request: Request, db: AsyncSession, invoice_id: int, checker: PermissionChecker
    ) -> None:
        super().__init__(request=request)
        self.invoice_id = invoice_id
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        invoice = await self.db.get(Invoice, self.invoice_id)
        if invoice is None or invoice.user_id != int(self.checker.user_id):
            self.not_found("发票不存在")
            return
        if not invoice.external_url:
            self.not_found("发票文件暂不可用")
            return

        if self._audit_context:
            self._audit_context.category = AuditCategoryEnum.SUBSCRIPTION
            self._audit_context.actor_type = ActorTypeEnum.USER
            self._audit_context.actor_id = self.checker.user_id
        self.set_audit_resource_id(str(invoice.id))
        self.operating_successfully(
            InvoiceDownloadResponseData(
                invoiceNo=invoice.invoice_no,
                filename=f"{invoice.invoice_no}.pdf",
                contentType="application/pdf",
                url=invoice.external_url,
            )
        )


class ChangePlanViewModel(BaseViewModel):
    """套餐变更兼容入口：付费套餐必须走 Stripe Checkout。"""

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "subscription"
    audit_enabled = True

    def __init__(self, request: Request, db: AsyncSession, form: ChangePlanForm, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return
        target = self.form.targetPlan
        if target == PlanEnum.FREE:
            self.illegal_parameters("降级为免费版请走取消订阅")
            return
        if target == user.plan:
            self.nothing_changed()
            return
        self.illegal_parameters("付费套餐必须通过结账流程完成支付")


class CancelSubscriptionViewModel(BaseViewModel):
    """取消订阅（POST /subscription/cancel）：撤销 active 订阅并降回免费套餐。

    若订阅由 Stripe 管理（有 stripe_subscription_id 且已启用 Stripe），先取消 Stripe 侧订阅，
    避免本地降级后 Stripe 继续扣费。
    """

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "subscription"
    audit_enabled = True

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return
        actives = (
            await self.db.scalars(
                select(Subscription).where(
                    Subscription.user_id == user.id,
                    Subscription.status == SubscriptionStatusEnum.ACTIVE,
                )
            )
        ).all()
        if not actives and user.plan == PlanEnum.FREE:
            self.nothing_changed()
            return

        for sub in actives:
            if sub.stripe_subscription_id and billing.stripe_enabled():
                try:
                    billing.cancel_subscription(sub.stripe_subscription_id)
                except Exception as exc:
                    logger.error(f"stripe 订阅取消失败({sub.stripe_subscription_id}): {exc}")
                    self.system_error("取消订阅失败，请稍后重试或通过客户门户操作")
                    return

        now = datetime.now(UTC)
        for sub in actives:
            sub.status = SubscriptionStatusEnum.CANCELED
            sub.canceled_at = now
        user.plan = PlanEnum.FREE
        await self.db.commit()
        if self._audit_context:
            self._audit_context.category = AuditCategoryEnum.SUBSCRIPTION
            self._audit_context.actor_type = ActorTypeEnum.USER
            self._audit_context.actor_id = self.checker.user_id
        self.operating_successfully({})


class CreateCheckoutViewModel(BaseViewModel):
    """发起套餐升级 / 切换：创建 Stripe Checkout 会话返回跳转 URL。"""

    def __init__(self, request: Request, db: AsyncSession, form: ChangePlanForm, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        target = self.form.targetPlan
        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return
        if target == PlanEnum.FREE:
            self.illegal_parameters("降级为免费版请走取消订阅")
            return
        if target == user.plan:
            self.nothing_changed()
            return
        plan = await _get_plan(self.db, target)
        if plan is None:
            self.not_found("目标套餐不存在")
            return

        cycle = self.form.billingCycle
        if not billing.stripe_enabled():
            self.illegal_parameters("未启用 Stripe 结账，无法切换付费套餐")
            return
        price_id = plan.stripe_price_yearly_id if cycle == BillingCycleEnum.YEARLY else plan.stripe_price_monthly_id
        if not price_id:
            self.illegal_parameters("该套餐 / 计费周期尚未同步到 Stripe，请先在后台同步")
            return

        customer_id = billing.ensure_customer(
            customer_id=user.stripe_customer_id,
            email=user.email,
            name=user.display_name,
            user_id=str(user.id),
        )
        if customer_id != user.stripe_customer_id:
            user.stripe_customer_id = customer_id
            await self.db.commit()
        base = get_settings().frontend_base_url
        _session_id, checkout_url = billing.create_checkout_session(
            customer_id=customer_id,
            price_id=price_id,
            success_url=f"{base}/user?billing=success",
            cancel_url=f"{base}/pricing?billing=cancel",
            metadata={"userId": str(user.id), "plan": target.value, "cycle": cycle.value},
        )
        self.operating_successfully(
            CheckoutResponseData(mode="checkout", checkoutUrl=checkout_url, subscription=None)
        )


class CreatePortalViewModel(BaseViewModel):
    """创建 Stripe Customer Portal 会话（管理订阅 / 支付方式 / 发票）。需已启用 Stripe 且已有客户。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return
        if not billing.stripe_enabled():
            self.illegal_parameters("未启用 Stripe 客户门户")
            return
        if not user.stripe_customer_id:
            self.illegal_parameters("当前账户无可管理的 Stripe 订阅")
            return
        portal_url = billing.create_billing_portal_session(
            customer_id=user.stripe_customer_id,
            return_url=f"{get_settings().frontend_base_url}/user",
        )
        self.operating_successfully(PortalResponseData(portalUrl=portal_url))


class StripeWebhookViewModel(BaseViewModel):
    """处理 Stripe Webhook：验签 → 按事件更新本地订阅 / 发票 / users.plan。公开端点（仅靠签名鉴别）。"""

    def __init__(self, request: Request, db: AsyncSession, payload: bytes, sig_header: str) -> None:
        super().__init__(request=request)
        self.db = db
        self.payload = payload
        self.sig_header = sig_header

    async def before(self) -> None:
        await super().before()
        try:
            event = billing.construct_webhook_event(self.payload, self.sig_header)
        except Exception as exc:
            logger.warning(f"stripe webhook 验签失败: {exc}")
            self.illegal_parameters("Webhook 验签失败")  # 路由层映射为 HTTP 400：密钥配错时 Stripe 侧可见失败
            return
        try:
            await self._dispatch(event)
        except Exception as exc:
            # 路由层映射为 HTTP 500，交给 Stripe 指数退避重试自愈瞬态故障；
            # 会话随请求回滚，处理器重放安全（checkout 全或无、发票按 invoice_no 去重）。
            logger.error(f"stripe webhook 处理异常: {exc}")
            self.system_error("Webhook 处理失败")
            return
        self.operating_successfully({"received": True})

    async def _dispatch(self, event: Any) -> None:
        event_type = str(event["type"])
        obj = event["data"]["object"]
        if event_type == "checkout.session.completed":
            await self._on_checkout_completed(obj)
        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            await self._on_subscription_change(obj, deleted=event_type.endswith("deleted"))
        elif event_type in ("invoice.paid", "invoice.payment_succeeded"):
            await self._on_invoice_paid(obj)

    async def _on_checkout_completed(self, session: Any) -> None:
        metadata = session.get("metadata") or {}
        user_id = metadata.get("userId")
        if not user_id:
            return
        user = await self.db.get(User, int(user_id))
        if user is None:
            return
        customer = session.get("customer")
        if customer:
            user.stripe_customer_id = str(customer)
        try:
            plan_enum = PlanEnum(metadata.get("plan", ""))
        except ValueError:
            await self.db.commit()
            return
        plan = await _get_plan(self.db, plan_enum)
        if plan is None:
            await self.db.commit()
            return
        cycle_value = metadata.get("cycle", "monthly")
        cycle = BillingCycleEnum.YEARLY if cycle_value == BillingCycleEnum.YEARLY.value else BillingCycleEnum.MONTHLY
        sub_id = session.get("subscription")
        await _apply_subscription_change(
            self.db,
            user,
            plan,
            cycle,
            stripe_subscription_id=str(sub_id) if sub_id else None,
            write_invoice=False,
        )

    async def _on_subscription_change(self, sub: Any, *, deleted: bool) -> None:
        sub_id = sub.get("id")
        if not sub_id:
            return
        local = await self.db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == str(sub_id)))
        if local is None:
            return
        user = await self.db.get(User, local.user_id)
        period_end = sub.get("current_period_end")
        if not period_end:
            # API 2025-03-31.basil 起该字段从 Subscription 顶层移至 items.data[].current_period_end
            items = (sub.get("items") or {}).get("data") or []
            period_end = items[0].get("current_period_end") if items else None
        if period_end:
            local.current_period_end = datetime.fromtimestamp(int(period_end), UTC)
        status = str(sub.get("status") or "")
        if deleted or status in ("canceled", "unpaid", "incomplete_expired"):
            local.status = SubscriptionStatusEnum.CANCELED
            local.canceled_at = datetime.now(UTC)
            if user is not None:
                user.plan = PlanEnum.FREE
        elif status in ("active", "trialing", "past_due"):
            local.status = SubscriptionStatusEnum.ACTIVE
        await self.db.commit()

    async def _on_invoice_paid(self, inv: Any) -> None:
        customer = inv.get("customer")
        if not customer:
            return
        user = await self.db.scalar(select(User).where(User.stripe_customer_id == str(customer)))
        if user is None:
            return
        invoice_no = str(inv.get("number") or inv.get("id") or "")
        if not invoice_no:
            return
        existing = await self.db.scalar(select(Invoice).where(Invoice.invoice_no == invoice_no))
        if existing is not None:
            return  # 幂等：同一发票号不重复落地。
        amount = float(inv.get("amount_paid", 0) or 0) / 100.0
        currency = str(inv.get("currency") or "usd").upper()
        external_url = inv.get("hosted_invoice_url") or inv.get("invoice_pdf")
        self.db.add(
            Invoice(
                user_id=user.id,
                subscription_id=None,
                invoice_no=invoice_no,
                plan_code=user.plan,
                item="subscription.invoice.subscription",
                amount=amount,
                currency=currency,
                status=InvoiceStatusEnum.PAID,
                issued_at=datetime.now(UTC),
                external_url=str(external_url) if external_url else None,
            )
        )
        await self.db.commit()


class _AdminSubscriptionViewModel(BaseViewModel):
    """订阅后台基类：统一管理员校验。"""

    checker: PermissionChecker

    def _require_admin(self) -> bool:
        self.checker.require_auth()
        if self.checker.user_type != UserTypeEnum.ADMIN:
            self.forbidden("仅管理员可访问")
            return False
        return True


class UpdatePlanViewModel(_AdminSubscriptionViewModel):
    """后台编辑套餐元数据（名称 / 标语 / 价格 / 特性 / 额度 / 排序 / 高亮），落库。仅管理员。"""

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "plan"
    audit_enabled = True

    def __init__(
        self, request: Request, db: AsyncSession, code: PlanEnum, form: PlanUpdateForm, checker: PermissionChecker
    ) -> None:
        super().__init__(request=request)
        self.code = code
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        plan = await _get_plan(self.db, self.code)
        if plan is None:
            self.not_found("套餐不存在")
            return
        form = self.form
        plan.name = form.name
        plan.tagline = form.tagline
        plan.price_monthly = form.priceMonthly
        plan.price_yearly_per_month = form.priceYearlyPerMonth
        plan.highlight = form.highlight
        plan.features = list(form.features)
        plan.limit_bots = form.limitBots
        plan.limit_strategies = form.limitStrategies
        plan.limit_ai_analysis = form.limitAiAnalysis
        plan.limit_backtests = form.limitBacktests
        plan.sort_order = form.sortOrder
        await self.db.commit()
        await self.db.refresh(plan)
        self.set_audit_resource_id(plan.code.value)
        self.operating_successfully(_build_plan_response(plan))


class SyncPlanToStripeViewModel(_AdminSubscriptionViewModel):
    """后台「同步到 Stripe」：创建 / 更新 Product + 月付 / 年付 Price，回填价格 ID 到 plans 表。仅管理员。"""

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "plan"
    audit_enabled = True

    def __init__(self, request: Request, db: AsyncSession, code: PlanEnum, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.code = code
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        if not billing.stripe_enabled():
            self.system_error("支付服务未配置（缺少 STRIPE_SECRET_KEY）")
            return
        plan = await _get_plan(self.db, self.code)
        if plan is None:
            self.not_found("套餐不存在")
            return
        if float(plan.price_monthly) <= 0 and float(plan.price_yearly_per_month) <= 0:
            self.illegal_parameters("免费套餐无需同步到 Stripe")
            return

        result = billing.sync_plan_to_stripe(
            code=plan.code.value,
            name=f"StratArk {plan.code.value.upper()}",
            price_monthly=float(plan.price_monthly),
            price_yearly_per_month=float(plan.price_yearly_per_month),
            product_id=plan.stripe_product_id,
            price_monthly_id=plan.stripe_price_monthly_id,
            price_yearly_id=plan.stripe_price_yearly_id,
        )
        plan.stripe_product_id = result["product_id"]
        plan.stripe_price_monthly_id = result["price_monthly_id"]
        plan.stripe_price_yearly_id = result["price_yearly_id"]
        await self.db.commit()
        await self.db.refresh(plan)
        self.set_audit_resource_id(plan.code.value)
        self.set_audit_metadata("stripeProductId", str(plan.stripe_product_id))
        self.operating_successfully(_build_plan_response(plan))
