"""计费 / 发票服务（Stripe 订阅 Checkout + Customer Portal + Webhook；config 驱动 + mock 回退）。

- 配置了 ``STRIPE_SECRET_KEY`` 时：经官方 stripe SDK 创建订阅 Checkout 会话 / 客户门户会话、
  校验 Webhook 签名；订阅激活与发票以 Stripe Webhook 为准（异步流程，源真相在 Stripe）。
- 未配置 Stripe 时：回退到本地 mock（``simulate_subscription_charge`` 即时成功 +
  ``render_invoice_document`` 文本占位），应用仍可运行、演示流程不变。

签名 / 密钥 / Webhook 验签只在后端；前端只拿后端返回的跳转 URL，不接触任何密钥。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import stripe

from configs import get_settings
from libs.logger import logger

__all__ = (
    "InvoiceDocumentResult",
    "SubscriptionChargeResult",
    "construct_webhook_event",
    "create_billing_portal_session",
    "create_checkout_session",
    "ensure_customer",
    "price_id_for",
    "render_invoice_document",
    "simulate_subscription_charge",
    "stripe_enabled",
)


@dataclass(slots=True)
class SubscriptionChargeResult:
    """模拟下单结果。

    真实实现：调用支付服务创建订阅订单并返回交易号；当前阶段恒为成功且零真实扣费。
    """

    ok: bool
    amount: float
    currency: str
    # 模拟交易号（真实实现为支付服务返回的订单 / 交易标识）。
    transaction_no: str
    message: str
    charged_at: datetime


@dataclass(slots=True)
class InvoiceDocumentResult:
    """发票文件产出结果。

    真实实现：由发票服务渲染 PDF 并返回字节流或对象存储下载链接；此处给出占位字节内容。
    """

    filename: str
    content_type: str
    # 模拟发票文件字节内容（真实实现为 PDF 二进制）。
    content: bytes
    size_bytes: int


def simulate_subscription_charge(
    plan_code: str,
    amount: float,
    currency: str = "USD",
    *,
    billing_cycle: str = "monthly",
) -> SubscriptionChargeResult:
    """模拟订阅扣费（无真实支付）。

    免费套餐（amount<=0）直接返回零额成功；付费套餐返回拟真交易号。
    真实实现：用支付服务下单并轮询 / 回调确认支付状态。
    """
    now = datetime.now(UTC)
    transaction_no = f"SIM-{plan_code.upper()}-{now.strftime('%Y%m%d%H%M%S')}"
    message = "免费套餐无需支付" if amount <= 0 else "模拟扣费成功 · 未产生真实费用"
    return SubscriptionChargeResult(
        ok=True,
        amount=amount,
        currency=currency,
        transaction_no=transaction_no,
        message=message,
        charged_at=now,
    )


def render_invoice_document(
    invoice_no: str,
    *,
    item: str,
    amount: float,
    currency: str = "USD",
) -> InvoiceDocumentResult:
    """生成可下载发票文件（mock 文本占位）。

    真实实现：发票服务按模板渲染 PDF；此处返回纯文本字节，前端可直接下载。
    """
    lines = [
        "StratArk Invoice (模拟发票 · 非真实付款凭证)",
        f"Invoice No: {invoice_no}",
        f"Item: {item}",
        f"Amount: {amount:.2f} {currency}",
        "Status: PAID (simulated)",
        "本发票为演示环境生成，不代表任何真实交易。",
    ]
    content = ("\n".join(lines)).encode("utf-8")
    return InvoiceDocumentResult(
        filename=f"{invoice_no}.txt",
        content_type="text/plain; charset=utf-8",
        content=content,
        size_bytes=len(content),
    )


# ============================ Stripe 集成（config 驱动，未配置不触达） ============================


def stripe_enabled() -> bool:
    """是否已配置 Stripe（未配置则订阅走 mock 回退）。"""
    return bool(get_settings().STRIPE_SECRET_KEY)


def _init_stripe() -> None:
    """调用前设置 stripe SDK 密钥。"""
    stripe.api_key = get_settings().STRIPE_SECRET_KEY


def price_id_for(plan_code: str, billing_cycle: str) -> str | None:
    """套餐 × 计费周期 → Stripe Price ID（取自 settings；免费套餐 / 未配置返回 None）。"""
    return getattr(get_settings(), f"STRIPE_PRICE_{plan_code.upper()}_{billing_cycle.upper()}", None)


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


def create_billing_portal_session(*, customer_id: str, return_url: str) -> str:
    """创建 Customer Portal 会话（管理订阅 / 支付方式 / 发票），返回门户 URL。"""
    _init_stripe()
    session = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return str(session["url"])


def construct_webhook_event(payload: bytes, sig_header: str) -> Any:
    """校验 Stripe-Signature 并构造 Webhook 事件（验签失败抛 stripe 异常，由调用方拦截）。"""
    _init_stripe()
    return stripe.Webhook.construct_event(payload, sig_header, get_settings().STRIPE_WEBHOOK_SECRET)
