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
    "CurrentSubscriptionResponseData",
    "InvoiceDownloadResponseData",
    "InvoiceResponseData",
    "PlanResponseData",
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
    name: str = Field(..., description="套餐名称（中文源串）")
    tagline: str = Field(..., description="套餐标语")
    priceMonthly: float = Field(..., description="月付价（美元 / 月）")
    priceYearlyPerMonth: float = Field(..., description="年付折合每月价")
    highlight: bool = Field(..., description="是否推荐高亮")
    features: list[str] = Field(..., description="特性条目（中文源串）")
    limits: PlanLimitsResponseData = Field(..., description="额度上限")


class UsageBarResponseData(ApiResponseModel):
    """本月用量条（与前端 UsageBar 对齐）。"""

    metric: UsageMetricEnum = Field(..., description="用量维度")
    label: str = Field(..., description="展示标签（中文源串）")
    used: int = Field(..., description="已用量")
    limit: int = Field(..., description="额度上限（-1 表示无限制）")
    value: str = Field(..., description="展示文案，如 2 / 10 或 无限制")
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
    """发票下载产物（base64 占位，真实实现为 PDF 下载链接）。"""

    invoiceNo: str = Field(..., description="发票号")
    filename: str = Field(..., description="文件名")
    contentType: str = Field(..., description="内容类型")
    contentBase64: str = Field(..., description="文件内容 base64 编码")
    sizeBytes: int = Field(..., description="文件字节数")
