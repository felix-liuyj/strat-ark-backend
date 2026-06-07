"""订阅域请求表单。"""

from fastapi import Body

from libs.schema import ApiFormModel
from models.account import PlanEnum
from models.subscription import BillingCycleEnum

__all__ = ("ChangePlanForm",)


class ChangePlanForm(ApiFormModel):
    """切换套餐（升级 / 降级）。

    target 为目标套餐；切到 free 等价于取消订阅（由取消端点单独处理，这里仅付费套餐间或升级）。
    billingCycle 决定按月或按年计价（模拟，不接入真实支付）。
    """

    targetPlan: PlanEnum = Body(..., embed=True, description="目标套餐：free / pro / team")
    billingCycle: BillingCycleEnum = Body(
        BillingCycleEnum.MONTHLY, embed=True, description="计费周期：monthly / yearly"
    )
