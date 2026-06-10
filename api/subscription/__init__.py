"""订阅域 API 路由：套餐目录 / 当前订阅 / 用量 / 账单 / Stripe Checkout / 客户门户 / Webhook / 后台套餐管理。"""

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from forms.subscription import ChangePlanForm, PlanUpdateForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, ResponseStatusCodeEnum, create_response
from models.account import PlanEnum
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
    SyncPlanToStripeViewModel,
    UpdatePlanViewModel,
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
    summary="即时变更套餐（未启用 Stripe）",
    description="未配置 Stripe 时本地即时切换套餐并返回最新订阅概况；已启用 Stripe 时拒绝（必须走结账流程）。",
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
    "/subscription/cancel",
    response_model=BaseResponseModel[dict],
    summary="取消订阅",
    description="撤销当前 active 订阅并降回免费套餐；由 Stripe 管理的订阅会先取消 Stripe 侧再落地本地。",
    tags=["StratArk/订阅计费"],
)
async def cancel_subscription(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CancelSubscriptionViewModel, request, db, checker=checker)


@router.post(
    "/subscription/checkout",
    response_model=BaseResponseModel[CheckoutResponseData],
    summary="发起套餐升级 / 切换（Stripe Checkout）",
    description="已配 Stripe 创建订阅 Checkout 会话返回跳转 URL（mode=checkout，激活以 Webhook 为准）；"
    "未配 Stripe 回退本地即时生效（mode=applied）。",
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
    description="返回指定发票的 Stripe 托管 PDF 链接（前端新开窗口打开）。",
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


@router.put(
    "/admin/plans/{code}",
    response_model=BaseResponseModel[PlanResponseData],
    summary="后台编辑套餐（管理员）",
    description="编辑套餐元数据（名称 / 标语 / 价格 / 特性 / 额度 / 排序 / 高亮）并落库。仅管理员。",
    tags=["StratArk/订阅计费"],
)
async def update_plan(
    request: Request,
    form: PlanUpdateForm,
    code: PlanEnum = Path(..., description="套餐标识：free / pro / team"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(UpdatePlanViewModel, request, db, code=code, form=form, checker=checker)


@router.post(
    "/admin/plans/{code}/sync",
    response_model=BaseResponseModel[PlanResponseData],
    summary="同步套餐到 Stripe（管理员）",
    description="将该套餐创建 / 更新为 Stripe Product + 月付 / 年付 Price，并回填价格 ID 到 plans 表。仅管理员。",
    tags=["StratArk/订阅计费"],
)
async def sync_plan_to_stripe(
    request: Request,
    code: PlanEnum = Path(..., description="套餐标识：pro / team（免费套餐无需同步）"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(SyncPlanToStripeViewModel, request, db, code=code, checker=checker)


@router.post(
    "/webhooks/stripe",
    response_model=BaseResponseModel[dict],
    summary="Stripe Webhook 回调",
    description="接收 Stripe 事件（checkout.session.completed / customer.subscription.* / invoice.paid）。"
    "公开端点，仅靠 Stripe-Signature 验签鉴别；在 Stripe 控制台注册指向本路径。"
    "对外契约由 Stripe 定义：验签失败回 HTTP 400，处理失败回 HTTP 500 触发 Stripe 重试。",
    tags=["StratArk/订阅计费"],
)
async def stripe_webhook(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    result = await create_response(
        StripeWebhookViewModel, request, db, payload=payload, sig_header=sig_header
    )
    # Stripe 只认 HTTP 状态码（2xx=已投递不重试），业务码壳对它不可见，须映射为真实状态
    if result.code == ResponseStatusCodeEnum.ILLEGAL_PARAMETERS:
        response.status_code = 400
    elif result.code == ResponseStatusCodeEnum.SYSTEM_ERROR:
        response.status_code = 500
    return result
