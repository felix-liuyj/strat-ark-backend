"""订阅域响应数据模型。

字段与前端 ``plans.ts`` / ``UserCenterPage`` 套餐与用量面板对齐：
套餐目录、当前订阅、本月用量条、账单发票历史。
"""

from pydantic import Field

from libs.schema import ApiResponseModel
from models.account import PlanEnum
from models.subscription import (
    BillingCycleEnum,
    InvoiceStatusEnum,
    SubscriptionStatusEnum,
    UsageMetricEnum,
)

__all__ = (
    "CheckoutResponseData",
    "CurrentSubscriptionResponseData",
    "InvoiceDownloadResponseData",
    "InvoiceResponseData",
    "PlanResponseData",
    "PortalResponseData",
    "UsageBarResponseData",
)


class PlanLimitsResponseData(ApiResponseModel):
    """套餐额度上限（-1 表示无限制）。"""

    bots: int = Field(..., description="交易机器人上限")
    strategies: int = Field(..., description="策略上限")
    aiAnalysis: int = Field(..., description="每月 AI 分析次数上限")
    backtests: int = Field(..., description="每月回测次数上限")


class PlanResponseData(ApiResponseModel):
    """单个套餐定义（与前端 PlanDef 对齐）。"""

    id: PlanEnum = Field(..., description="套餐标识")
    name: str = Field(..., description="套餐名称 i18n key")
    tagline: str = Field(..., description="套餐标语 i18n key")
    priceMonthly: float = Field(..., description="月付价（美元 / 月）")
    priceYearlyPerMonth: float = Field(..., description="年付折合每月价")
    highlight: bool = Field(..., description="是否推荐高亮")
    features: list[str] = Field(..., description="特性条目 i18n key 列表")
    limits: PlanLimitsResponseData = Field(..., description="额度上限")


class UsageBarResponseData(ApiResponseModel):
    """本月用量条（与前端 UsageBar 对齐）。"""

    metric: UsageMetricEnum = Field(..., description="用量维度")
    label: str = Field(..., description="展示标签 i18n key")
    used: int = Field(..., description="已用量")
    limit: int = Field(..., description="额度上限（-1 表示无限制）")
    value: str = Field(..., description="展示值；数字比例为原样字符串，无限制等文案返回 i18n key")
    width: str = Field(..., description="进度条宽度百分比，如 20%")


class CurrentSubscriptionResponseData(ApiResponseModel):
    """当前订阅概况。"""

    planCode: PlanEnum = Field(..., description="当前套餐")
    status: SubscriptionStatusEnum = Field(..., description="订阅状态")
    billingCycle: BillingCycleEnum = Field(..., description="计费周期")
    unitPrice: float = Field(..., description="周期单价快照")
    startedAt: str | None = Field(None, description="开始时间")
    currentPeriodEnd: str | None = Field(None, description="下次续费时间")
    canceledAt: str | None = Field(None, description="取消时间")
    stripeEnabled: bool = Field(False, description="是否已启用 Stripe（前端据此决定走 Checkout/Portal 还是即时 mock）")


class InvoiceResponseData(ApiResponseModel):
    """账单 / 发票记录（与前端 Billing 表对齐）。"""

    id: int = Field(..., description="发票 ID")
    invoiceNo: str = Field(..., description="发票号")
    planCode: PlanEnum = Field(..., description="对应套餐")
    item: str = Field(..., description="项目说明")
    amount: float = Field(..., description="金额")
    currency: str = Field(..., description="币种")
    status: InvoiceStatusEnum = Field(..., description="发票状态")
    issuedAt: str | None = Field(None, description="开具时间")


class InvoiceDownloadResponseData(ApiResponseModel):
    """发票下载产物：Stripe 发票返回托管 PDF 链接(url)，mock 发票返回 base64 文本占位。"""

    invoiceNo: str = Field(..., description="发票号")
    filename: str = Field(..., description="文件名")
    contentType: str = Field(..., description="内容类型")
    contentBase64: str = Field("", description="文件内容 base64 编码（mock 占位；Stripe 路径为空）")
    sizeBytes: int = Field(0, description="文件字节数")
    url: str | None = Field(None, description="Stripe 托管发票 PDF 链接（存在则前端优先打开）")


class CheckoutResponseData(ApiResponseModel):
    """套餐变更结果：Stripe 已启用时返回 Checkout 跳转 URL；否则即时应用并返回当前订阅。"""

    mode: str = Field(..., description="checkout=需跳转 Stripe 支付；applied=已即时应用(mock)")
    checkoutUrl: str | None = Field(None, description="Stripe Checkout 跳转地址（mode=checkout）")
    subscription: CurrentSubscriptionResponseData | None = Field(
        None, description="即时应用后的当前订阅（mode=applied）"
    )


class PortalResponseData(ApiResponseModel):
    """Stripe Customer Portal 跳转地址（管理订阅 / 支付方式 / 发票）。"""

    portalUrl: str = Field(..., description="客户门户跳转地址")
