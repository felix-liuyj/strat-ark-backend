"""订阅域 ViewModel：套餐目录 / 当前订阅 / 切换 / 取消 / 用量 / 账单 / 发票下载。

切换与取消仅更新本地 ``Subscription`` 记录与 ``users.plan``，并写审计；
绝不接入真实支付（扣费由 ``libs.integrations.billing`` service stub 模拟）。
"""

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from configs import get_settings
from forms.subscription import ChangePlanForm
from libs.auth.permissions import PermissionChecker
from libs.integrations import billing
from libs.integrations.billing import render_invoice_document, simulate_subscription_charge
from libs.logger import logger
from libs.sso import AUTH_INVALID_MESSAGE
from models.account import PlanEnum
from models.audit_log import ActorTypeEnum, AuditActionEnum, AuditCategoryEnum
from models.subscription import (
    BillingCycleEnum,
    Invoice,
    InvoiceStatusEnum,
    Plan,
    Subscription,
    SubscriptionStatusEnum,
    UsageCounter,
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

# 各套餐默认用量种子（演示数据，与前端 usageForPlan 占比一致）。
_USAGE_SEED: dict[PlanEnum, dict[UsageMetricEnum, int]] = {
    PlanEnum.FREE: {
        UsageMetricEnum.BOTS: 1,
        UsageMetricEnum.STRATEGIES: 2,
        UsageMetricEnum.AI_ANALYSIS: 14,
        UsageMetricEnum.BACKTESTS: 6,
    },
    PlanEnum.PRO: {
        UsageMetricEnum.BOTS: 2,
        UsageMetricEnum.STRATEGIES: 4,
        UsageMetricEnum.AI_ANALYSIS: 186,
        UsageMetricEnum.BACKTESTS: 0,
    },
    PlanEnum.TEAM: {
        UsageMetricEnum.BOTS: 12,
        UsageMetricEnum.STRATEGIES: 28,
        UsageMetricEnum.AI_ANALYSIS: 640,
        UsageMetricEnum.BACKTESTS: 0,
    },
}


def _current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


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


async def _apply_local_change(
    db: AsyncSession,
    user: User,
    plan: Plan,
    cycle: BillingCycleEnum,
    *,
    stripe_subscription_id: str | None = None,
    write_invoice: bool = True,
) -> Subscription:
    """本地应用套餐变更：撤销旧 active 订阅 → 写新 active 订阅(+可选已支付发票) → 更新 users.plan。

    用于未配置 Stripe 的即时 mock 路径，以及 Stripe Webhook 激活订阅（传 write_invoice=False，
    发票由 invoice.paid 事件单独落地、带托管 PDF 链接）。
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
            CurrentSubscriptionResponseData(
                planCode=user.plan,
                status=sub.status if sub else SubscriptionStatusEnum.ACTIVE,
                billingCycle=sub.billing_cycle if sub else BillingCycleEnum.MONTHLY,
                unitPrice=float(sub.unit_price) if sub else unit_price,
                startedAt=_iso_or_none(sub.started_at) if sub else None,
                currentPeriodEnd=_iso_or_none(sub.current_period_end) if sub else None,
                canceledAt=_iso_or_none(sub.canceled_at) if sub else None,
                stripeEnabled=billing.stripe_enabled(),
            )
        )


class ChangePlanViewModel(BaseViewModel):
    """切换套餐（升级 / 降级）。

    target=free 视为取消（引导走取消端点）；付费目标套餐：把旧 active 订阅置为
    canceled，写新 active 订阅，更新 users.plan，生成已支付发票（模拟，无真实扣费），写审计。
    """

    audit_action = AuditActionEnum.SUBSCRIBE
    audit_resource = "subscription"
    audit_enabled = True

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: ChangePlanForm,
        checker: PermissionChecker,
    ) -> None:
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
            self.illegal_parameters("降级为免费版请调用取消订阅接口")
            return

        if target == user.plan:
            self.nothing_changed()
            return

        plan = await _get_plan(self.db, target)
        if plan is None:
            self.not_found("目标套餐不存在")
            return

        old_plan = user.plan
        cycle = self.form.billingCycle
        unit_price = (
            float(plan.price_yearly_per_month)
            if cycle == BillingCycleEnum.YEARLY
            else float(plan.price_monthly)
        )

        charge = simulate_subscription_charge(
            target.value, unit_price, "USD", billing_cycle=cycle.value
        )

        now = datetime.now(UTC)
        await self._cancel_active_subscriptions(user.id, now)

        period_days = 365 if cycle == BillingCycleEnum.YEARLY else 30
        subscription = Subscription(
            user_id=user.id,
            plan_code=target,
            billing_cycle=cycle,
            status=SubscriptionStatusEnum.ACTIVE,
            unit_price=unit_price,
            started_at=now,
            current_period_end=now + timedelta(days=period_days),
        )
        self.db.add(subscription)
        await self.db.flush()

        invoice = self._build_invoice(user.id, subscription.id, plan, unit_price)
        self.db.add(invoice)

        user.plan = target
        await self.db.commit()

        direction = "升级" if _PLAN_ORDER[target] > _PLAN_ORDER[old_plan] else "降级"
        self._record_audit(user, old_plan, target, direction, charge.transaction_no)
        await self.db.refresh(subscription)
        self.operating_successfully(
            CurrentSubscriptionResponseData(
                planCode=user.plan,
                status=subscription.status,
                billingCycle=subscription.billing_cycle,
                unitPrice=float(subscription.unit_price),
                startedAt=_iso_or_none(subscription.started_at),
                currentPeriodEnd=_iso_or_none(subscription.current_period_end),
                canceledAt=None,
                stripeEnabled=billing.stripe_enabled(),
            )
        )

    async def _cancel_active_subscriptions(self, user_id: int, now: datetime) -> None:
        actives = (
            await self.db.scalars(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.status == SubscriptionStatusEnum.ACTIVE,
                )
            )
        ).all()
        for sub in actives:
            sub.status = SubscriptionStatusEnum.CANCELED
            sub.canceled_at = now

    def _build_invoice(self, user_id: int, subscription_id: int, plan: Plan, amount: float) -> Invoice:
        now = datetime.now(UTC)
        invoice_no = f"INV-{now.strftime('%Y%m')}-{now.strftime('%d%H%M%S')}"
        return Invoice(
            user_id=user_id,
            subscription_id=subscription_id,
            invoice_no=invoice_no,
            plan_code=plan.code,
            item="subscription.invoice.subscription",
            amount=amount,
            currency="USD",
            status=InvoiceStatusEnum.PAID,
            issued_at=now,
        )

    def _record_audit(
        self, user: User, old_plan: PlanEnum, target: PlanEnum, direction: str, transaction_no: str
    ) -> None:
        if self._audit_context:
            self._audit_context.category = AuditCategoryEnum.SUBSCRIPTION
            self._audit_context.actor_type = ActorTypeEnum.USER
            self._audit_context.actor_id = str(user.id)
            self._audit_context.actor_name = user.display_name or user.email
            self._audit_context.message = f"{direction}套餐 {old_plan.value} → {target.value}"
        self.set_audit_resource_id(str(user.id))
        self.set_audit_changes({"plan": {"old": old_plan.value, "new": target.value}})
        self.set_audit_metadata("transactionNo", transaction_no)


class CancelSubscriptionViewModel(BaseViewModel):
    """取消订阅 → 降级为免费版（模拟，不涉及真实退款），写审计。"""

    audit_action = AuditActionEnum.CANCEL
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

        if user.plan == PlanEnum.FREE:
            self.nothing_changed()
            return

        old_plan = user.plan
        now = datetime.now(UTC)
        actives = (
            await self.db.scalars(
                select(Subscription).where(
                    Subscription.user_id == user.id,
                    Subscription.status == SubscriptionStatusEnum.ACTIVE,
                )
            )
        ).all()
        for sub in actives:
            sub.status = SubscriptionStatusEnum.CANCELED
            sub.canceled_at = now

        user.plan = PlanEnum.FREE
        await self.db.commit()

        if self._audit_context:
            self._audit_context.category = AuditCategoryEnum.SUBSCRIPTION
            self._audit_context.actor_type = ActorTypeEnum.USER
            self._audit_context.actor_id = str(user.id)
            self._audit_context.actor_name = user.display_name or user.email
            self._audit_context.message = f"取消订阅，{old_plan.value} → free"
        self.set_audit_resource_id(str(user.id))
        self.set_audit_changes({"plan": {"old": old_plan.value, "new": PlanEnum.FREE.value}})
        self.operating_successfully()


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

        counters = await self._ensure_usage_seeded(user.id, user.plan)
        bars = [self._build_bar(plan, metric, counters.get(metric, 0)) for metric in UsageMetricEnum]
        self.operating_successfully(bars)

    async def _ensure_usage_seeded(
        self, user_id: int, plan_code: PlanEnum
    ) -> dict[UsageMetricEnum, int]:
        period = _current_period()
        existing = (
            await self.db.scalars(
                select(UsageCounter).where(
                    UsageCounter.user_id == user_id,
                    UsageCounter.period == period,
                )
            )
        ).all()
        if existing:
            return {UsageMetricEnum(c.metric): c.used for c in existing}

        seed = _USAGE_SEED.get(plan_code, _USAGE_SEED[PlanEnum.FREE])
        for metric, used in seed.items():
            self.db.add(UsageCounter(user_id=user_id, metric=metric, period=period, used=used))
        await self.db.commit()
        return dict(seed)

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
    """发票下载（service stub 生成占位文件，base64 返回）。"""

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

        if self._audit_context:
            self._audit_context.category = AuditCategoryEnum.SUBSCRIPTION
            self._audit_context.actor_type = ActorTypeEnum.USER
            self._audit_context.actor_id = self.checker.user_id
        self.set_audit_resource_id(str(invoice.id))

        # Stripe 发票：直接返回托管 PDF 链接，前端新开窗口打开；mock 发票返回 base64 文本占位。
        if invoice.external_url:
            self.operating_successfully(
                InvoiceDownloadResponseData(
                    invoiceNo=invoice.invoice_no,
                    filename=f"{invoice.invoice_no}.pdf",
                    contentType="application/pdf",
                    url=invoice.external_url,
                )
            )
            return

        doc = render_invoice_document(
            invoice.invoice_no,
            item=invoice.item,
            amount=float(invoice.amount),
            currency=invoice.currency,
        )
        self.operating_successfully(
            InvoiceDownloadResponseData(
                invoiceNo=invoice.invoice_no,
                filename=doc.filename,
                contentType=doc.content_type,
                contentBase64=base64.b64encode(doc.content).decode("ascii"),
                sizeBytes=doc.size_bytes,
            )
        )


class CreateCheckoutViewModel(BaseViewModel):
    """发起套餐变更：Stripe 已启用 → 创建订阅 Checkout 会话返回跳转 URL；未启用 → 即时应用(mock)。"""

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
            self.illegal_parameters("降级为免费版请使用取消订阅 / 客户门户")
            return
        if target == user.plan:
            self.nothing_changed()
            return
        plan = await _get_plan(self.db, target)
        if plan is None:
            self.not_found("目标套餐不存在")
            return

        cycle = self.form.billingCycle
        if billing.stripe_enabled():
            await self._start_checkout(user, target, cycle)
            return

        # 未配置 Stripe：即时应用 mock 变更，返回当前订阅。
        unit_price = float(plan.price_yearly_per_month) if cycle == BillingCycleEnum.YEARLY else float(plan.price_monthly)
        simulate_subscription_charge(target.value, unit_price, "USD", billing_cycle=cycle.value)
        subscription = await _apply_local_change(self.db, user, plan, cycle)
        self.operating_successfully(
            CheckoutResponseData(
                mode="applied",
                checkoutUrl=None,
                subscription=CurrentSubscriptionResponseData(
                    planCode=user.plan,
                    status=subscription.status,
                    billingCycle=subscription.billing_cycle,
                    unitPrice=float(subscription.unit_price),
                    startedAt=_iso_or_none(subscription.started_at),
                    currentPeriodEnd=_iso_or_none(subscription.current_period_end),
                    canceledAt=None,
                    stripeEnabled=False,
                ),
            )
        )

    async def _start_checkout(self, user: User, target: PlanEnum, cycle: BillingCycleEnum) -> None:
        price_id = billing.price_id_for(target.value, cycle.value)
        if not price_id:
            self.illegal_parameters("该套餐 / 计费周期未配置 Stripe 价格")
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
        self.operating_successfully(CheckoutResponseData(mode="checkout", checkoutUrl=checkout_url, subscription=None))


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
            self.illegal_parameters("Webhook 验签失败")
            return
        try:
            await self._dispatch(event)
        except Exception as exc:  # 处理异常仅记录、仍返回成功，避免向 Stripe 触发无谓重试风暴。
            logger.error(f"stripe webhook 处理异常: {exc}")
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
        await _apply_local_change(
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
