"""订阅域请求表单。"""

from fastapi import Body

from libs.schema import ApiFormModel
from models.account import PlanEnum
from models.subscription import BillingCycleEnum

__all__ = ("ChangePlanForm", "PlanUpdateForm")


class ChangePlanForm(ApiFormModel):
    """发起套餐升级 / 切换（目标付费套餐 + 计费周期），后端据此创建 Stripe Checkout 会话。"""

    targetPlan: PlanEnum = Body(..., embed=True, description="目标套餐：free / pro / team")
    billingCycle: BillingCycleEnum = Body(
        BillingCycleEnum.MONTHLY, embed=True, description="计费周期：monthly / yearly"
    )


class PlanUpdateForm(ApiFormModel):
    """后台编辑套餐元数据（全字段更新，落库 plans 表）。"""

    name: str = Body(..., embed=True, description="套餐名称 i18n key")
    tagline: str = Body(..., embed=True, description="套餐标语 i18n key")
    priceMonthly: float = Body(..., embed=True, description="月付价（美元 / 月）")
    priceYearlyPerMonth: float = Body(..., embed=True, description="年付折合每月价")
    highlight: bool = Body(False, embed=True, description="是否推荐高亮")
    features: list[str] = Body(..., embed=True, description="特性条目 i18n key 列表")
    limitBots: int = Body(..., embed=True, description="机器人上限（-1 表示无限制）")
    limitStrategies: int = Body(..., embed=True, description="策略上限（-1 无限制）")
    limitAiAnalysis: int = Body(..., embed=True, description="每月 AI 分析次数上限（-1 无限制）")
    limitBacktests: int = Body(..., embed=True, description="每月回测次数上限（-1 无限制）")
    sortOrder: int = Body(0, embed=True, description="排序")
