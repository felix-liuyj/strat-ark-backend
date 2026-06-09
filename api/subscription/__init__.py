"""订阅域 API 路由：套餐目录 / 当前订阅 / 切换 / 取消 / 用量 / 账单 / 发票下载。"""

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.subscription import ChangePlanForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.subscription import (
    CheckoutResponseData,
    CurrentSubscriptionResponseData,
    InvoiceDownloadResponseData,
    InvoiceResponseData,
    PlanResponseData,
    PortalResponseData,
    UsageBarResponseData,
)
from view_models.subscription import (
    CancelSubscriptionViewModel,
    ChangePlanViewModel,
    CreateCheckoutViewModel,
    CreatePortalViewModel,
    DownloadInvoiceViewModel,
    GetCurrentSubscriptionViewModel,
    ListInvoicesViewModel,
    ListPlansViewModel,
    ListUsageViewModel,
    StripeWebhookViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/plans",
    response_model=BaseResponseModel[list[PlanResponseData]],
    summary="获取套餐目录",
    description="返回 free / pro / team 三套餐定义（价格、特性、额度上限），公开可读，供定价页消费。",
    tags=["StratArk/订阅计费"],
)
async def list_plans(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListPlansViewModel, request, db)


@router.get(
    "/subscription",
    response_model=BaseResponseModel[CurrentSubscriptionResponseData],
    summary="获取当前订阅",
    description="返回当前登录用户的订阅概况（套餐、状态、计费周期、下次续费时间）。",
    tags=["StratArk/订阅计费"],
)
async def get_current_subscription(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetCurrentSubscriptionViewModel, request, db, checker=checker)


@router.post(
    "/subscription/change",
    response_model=BaseResponseModel[CurrentSubscriptionResponseData],
    summary="切换套餐（升级 / 降级）",
    description="切换到目标付费套餐，更新本地订阅与用户套餐并生成发票（模拟，不涉及真实支付）。降级为免费版请用取消接口。",
    tags=["StratArk/订阅计费"],
)
async def change_plan(
    request: Request,
    form: ChangePlanForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ChangePlanViewModel, request, db, checker=checker, form=form)


@router.post(
    "/subscription/checkout",
    response_model=BaseResponseModel[CheckoutResponseData],
    summary="发起套餐变更（Stripe Checkout / mock）",
    description="Stripe 已启用时创建订阅 Checkout 会话并返回跳转 URL（mode=checkout）；未启用时即时应用 mock 变更并返回当前订阅（mode=applied）。",
    tags=["StratArk/订阅计费"],
)
async def create_checkout(
    request: Request,
    form: ChangePlanForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateCheckoutViewModel, request, db, checker=checker, form=form)


@router.post(
    "/subscription/portal",
    response_model=BaseResponseModel[PortalResponseData],
    summary="打开 Stripe 客户门户",
    description="创建 Stripe Customer Portal 会话并返回跳转 URL，用于管理订阅 / 支付方式 / 发票。需已启用 Stripe 且账户已有 Stripe 客户。",
    tags=["StratArk/订阅计费"],
)
async def create_portal(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreatePortalViewModel, request, db, checker=checker)


@router.post(
    "/subscription/cancel",
    response_model=BaseResponseModel[None],
    summary="取消订阅",
    description="取消当前订阅并降级为免费版（模拟，不涉及真实退款）。",
    tags=["StratArk/订阅计费"],
)
async def cancel_subscription(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CancelSubscriptionViewModel, request, db, checker=checker)


@router.get(
    "/subscription/usage",
    response_model=BaseResponseModel[list[UsageBarResponseData]],
    summary="获取本月用量",
    description="返回当前套餐下本月各维度（机器人 / 策略 / AI 分析 / 回测）的用量条与占比。",
    tags=["StratArk/订阅计费"],
)
async def list_usage(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListUsageViewModel, request, db, checker=checker)


@router.get(
    "/invoices",
    response_model=BaseResponseModel[list[InvoiceResponseData]],
    summary="获取账单 / 发票历史",
    description="返回当前用户的账单与发票记录，按时间倒序。",
    tags=["StratArk/订阅计费"],
)
async def list_invoices(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListInvoicesViewModel, request, db, checker=checker)


@router.get(
    "/invoices/{invoice_id}/download",
    response_model=BaseResponseModel[InvoiceDownloadResponseData],
    summary="下载发票",
    description="生成并返回指定发票的可下载文件（service stub 占位，base64 编码）。",
    tags=["StratArk/订阅计费"],
)
async def download_invoice(
    request: Request,
    invoice_id: int = Path(..., description="发票 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        DownloadInvoiceViewModel, request, db, invoice_id=invoice_id, checker=checker
    )


@router.post(
    "/webhooks/stripe",
    response_model=BaseResponseModel[dict],
    summary="Stripe Webhook 回调",
    description="接收 Stripe 事件（checkout.session.completed / customer.subscription.* / invoice.paid）。"
    "公开端点，仅靠 Stripe-Signature 验签鉴别；在 Stripe 控制台注册指向本路径。",
    tags=["StratArk/订阅计费"],
)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    return await create_response(
        StripeWebhookViewModel, request, db, payload=payload, sig_header=sig_header
    )
