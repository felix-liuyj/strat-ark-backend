"""计费 / 发票服务 stub。

返回拟真 mock 数据；函数签名按真实计费集成（Stripe / 支付服务 + 发票生成）预留。
**绝不发起真实扣费、转账或支付**：套餐升级 / 降级 / 取消只在本地写订阅与发票记录，
本模块仅负责"模拟下单结果"与"生成可下载发票文件"两类纯产物。
真实实现时这里会调用支付服务创建订单 / 订阅，并由发票服务渲染 PDF。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

__all__ = (
    "InvoiceDocumentResult",
    "SubscriptionChargeResult",
    "render_invoice_document",
    "simulate_subscription_charge",
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
