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
    stripeEnabled: bool = Field(..., description="平台是否启用 Stripe（决定前端展示客户门户还是本地取消）")


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
    """发票下载产物：优先返回 Stripe 托管 PDF 链接（url），无链接时返回内联 base64 内容。"""

    invoiceNo: str = Field(..., description="发票号")
    filename: str = Field(..., description="文件名")
    contentType: str = Field(..., description="内容类型")
    contentBase64: str | None = Field(None, description="文件内容 base64（url 为空时提供）")
    sizeBytes: int | None = Field(None, description="文件字节数（contentBase64 提供时有值）")
    url: str | None = Field(None, description="Stripe 托管发票 PDF 链接")


class CheckoutResponseData(ApiResponseModel):
    """套餐切换结果：mode=checkout 时跳转 Stripe。"""

    mode: str = Field(..., description="结账模式：checkout（跳转 Stripe）")
    checkoutUrl: str | None = Field(None, description="Stripe Checkout 跳转地址（mode=checkout 时有值）")
    subscription: CurrentSubscriptionResponseData | None = Field(
        None, description="保留字段；订阅状态以 Stripe Webhook 回写后的 /subscription 为准"
    )


class PortalResponseData(ApiResponseModel):
    """Stripe Customer Portal 跳转地址（管理订阅 / 支付方式 / 发票）。"""

    portalUrl: str = Field(..., description="客户门户跳转地址")
