"""计费集成（Stripe 订阅 Checkout + Customer Portal + Webhook + 产品/价格同步）。

经官方 stripe SDK 实现订阅支付：创建客户、订阅 Checkout 会话、客户门户会话、Webhook 验签，
以及把后台落库的套餐同步为 Stripe Product + 周期 Price（价格 ID 回填到 plans 表）。

订阅激活与发票以 Stripe Webhook 为准（异步流程，源真相在 Stripe）。
签名 / 密钥 / Webhook 验签只在后端；前端只拿后端返回的跳转 URL，不接触任何密钥。
"""

from __future__ import annotations

from typing import Any

import stripe

from configs import get_settings
from libs.logger import logger

__all__ = (
    "cancel_subscription",
    "construct_webhook_event",
    "create_billing_portal_session",
    "create_checkout_session",
    "ensure_customer",
    "stripe_enabled",
    "sync_plan_to_stripe",
)


def stripe_enabled() -> bool:
    """是否已配置 Stripe 密钥（未配置时支付相关端点返回明确错误）。"""
    return bool(get_settings().STRIPE_SECRET_KEY)


def _init_stripe() -> None:
    """调用前设置 stripe SDK 密钥。"""
    stripe.api_key = get_settings().STRIPE_SECRET_KEY


def ensure_customer(*, customer_id: str | None, email: str, name: str, user_id: str) -> str:
    """返回可用的 Stripe Customer ID：已有直接用，否则按用户创建（幂等键防重复）。"""
    _init_stripe()
    if customer_id:
        return customer_id
    customer = stripe.Customer.create(
        email=email,
        name=name or email,
        metadata={"userId": user_id},
        idempotency_key=f"customer-{user_id}",
    )
    return str(customer["id"])


def create_checkout_session(
    *,
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    metadata: dict[str, str],
) -> tuple[str, str]:
    """创建订阅模式 Checkout 会话，返回 (session_id, checkout_url)。"""
    _init_stripe()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
        subscription_data={"metadata": metadata},
        allow_promotion_codes=True,
    )
    return str(session["id"]), str(session["url"])


def cancel_subscription(subscription_id: str) -> None:
    """立即取消 Stripe 订阅（本地取消前调用，避免本地降级后 Stripe 继续扣费）。"""
    _init_stripe()
    stripe.Subscription.cancel(subscription_id)


def create_billing_portal_session(*, customer_id: str, return_url: str) -> str:
    """创建 Customer Portal 会话（管理订阅 / 支付方式 / 发票），返回门户 URL。"""
    _init_stripe()
    session = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return str(session["url"])


def construct_webhook_event(payload: bytes, sig_header: str) -> Any:
    """校验 Stripe-Signature 并构造 Webhook 事件（验签失败抛 stripe 异常，由调用方拦截）。"""
    _init_stripe()
    return stripe.Webhook.construct_event(payload, sig_header, get_settings().STRIPE_WEBHOOK_SECRET)


def _ensure_price(
    product_id: str,
    existing_id: str | None,
    unit_amount: int,
    currency: str,
    interval: str,
) -> str | None:
    """确保产品在该计费周期下有匹配金额的 recurring Price：金额未变复用旧价，变更则新建并归档旧价。

    ``unit_amount`` 为「分」；<=0（免费 / 该周期无价）返回 None。
    """
    if unit_amount <= 0:
        return None
    if existing_id:
        try:
            existing = stripe.Price.retrieve(existing_id)
            recurring = existing.get("recurring") or {}
            if (
                int(existing.get("unit_amount") or 0) == unit_amount
                and recurring.get("interval") == interval
                and existing.get("active")
            ):
                return existing_id
        except Exception as exc:
            logger.warning(f"stripe price retrieve 失败({existing_id})，将新建: {exc}")
    price = stripe.Price.create(
        product=product_id,
        unit_amount=unit_amount,
        currency=currency,
        recurring={"interval": interval},
    )
    if existing_id and existing_id != price["id"]:
        try:
            stripe.Price.modify(existing_id, active=False)
        except Exception as exc:
            logger.warning(f"归档旧 stripe price 失败({existing_id}): {exc}")
    return str(price["id"])


def sync_plan_to_stripe(
    *,
    code: str,
    name: str,
    price_monthly: float,
    price_yearly_per_month: float,
    currency: str = "usd",
    product_id: str | None = None,
    price_monthly_id: str | None = None,
    price_yearly_id: str | None = None,
) -> dict[str, str | None]:
    """把后台落库的套餐同步到 Stripe：创建 / 更新 Product 与月付 / 年付 Price，返回回填用的 ID。

    年付 Price 的年度金额 = ``price_yearly_per_month * 12``。返回 {product_id, price_monthly_id,
    price_yearly_id}（免费 / 该周期金额为 0 时对应 price 为 None）。
    """
    _init_stripe()
    if product_id:
        product = stripe.Product.modify(product_id, name=name, active=True)
    else:
        product = stripe.Product.create(name=name, metadata={"planCode": code})
    resolved_product_id = str(product["id"])
    monthly_amount = round(float(price_monthly) * 100)
    yearly_amount = round(float(price_yearly_per_month) * 12 * 100)
    return {
        "product_id": resolved_product_id,
        "price_monthly_id": _ensure_price(resolved_product_id, price_monthly_id, monthly_amount, currency, "month"),
        "price_yearly_id": _ensure_price(resolved_product_id, price_yearly_id, yearly_amount, currency, "year"),
    }
