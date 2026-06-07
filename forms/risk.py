"""风控中心请求表单。

覆盖单条风控规则的创建 / 更新，以及前端「编辑风控规则」弹窗的批量阈值 + 开关下发。
Body 字段一律 camelCase，使用 Body(..., embed=True)。
"""

from fastapi import Body

from libs.schema import ApiFormModel
from models.risk import RiskEventLevelEnum, RiskRuleScopeEnum, RiskRuleTypeEnum

__all__ = (
    "RiskEventCreateForm",
    "RiskRuleCreateForm",
    "RiskRuleUpdateForm",
    "RiskRulesBulkUpdateForm",
)


class RiskRuleCreateForm(ApiFormModel):
    scope: RiskRuleScopeEnum = Body(..., embed=True, description="风控分层")
    ruleType: RiskRuleTypeEnum = Body(..., embed=True, description="规则类型")
    label: str = Body(..., embed=True, description="规则展示名")
    currentValue: float | None = Body(None, embed=True, description="当前值（阈值类）")
    limitValue: float | None = Body(None, embed=True, description="限额值（阈值类）")
    unit: str = Body("", embed=True, description="单位，如 % / x / 次")
    enabled: bool = Body(True, embed=True, description="是否启用")
    botId: int | None = Body(None, embed=True, description="绑定 Bot ID")
    strategyId: int | None = Body(None, embed=True, description="绑定策略 ID")
    symbol: str | None = Body(None, embed=True, description="绑定交易对")
    description: str = Body("", embed=True, description="规则说明")


class RiskRuleUpdateForm(ApiFormModel):
    label: str | None = Body(None, embed=True, description="规则展示名")
    currentValue: float | None = Body(None, embed=True, description="当前值")
    limitValue: float | None = Body(None, embed=True, description="限额值")
    unit: str | None = Body(None, embed=True, description="单位")
    enabled: bool | None = Body(None, embed=True, description="是否启用")
    description: str | None = Body(None, embed=True, description="规则说明")


class RiskRulesBulkUpdateForm(ApiFormModel):
    """前端「编辑风控规则」弹窗：六个阈值 + 三个过滤开关，一次下发全部 Bot。"""

    dailyLossLimit: float = Body(..., embed=True, description="每日亏损上限 %")
    maxDrawdown: float = Body(..., embed=True, description="最大回撤 %")
    maxPositionSize: float = Body(..., embed=True, description="单笔最大仓位 %")
    maxLeverage: float = Body(..., embed=True, description="最大杠杆")
    cooldownCount: int = Body(..., embed=True, description="连亏冷却次数")
    cooldownHours: float = Body(..., embed=True, description="冷却时长（小时）")
    newsFilter: bool = Body(True, embed=True, description="新闻风险过滤开关")
    volatilityFilter: bool = Body(True, embed=True, description="波动率过滤开关")
    liquidityFilter: bool = Body(True, embed=True, description="流动性过滤开关")


class RiskEventCreateForm(ApiFormModel):
    """落地一条风控触发记录（评估命中 / 拦截动作后调用）。"""

    level: RiskEventLevelEnum = Body(..., embed=True, description="事件级别")
    scope: RiskRuleScopeEnum = Body(RiskRuleScopeEnum.ACCOUNT, embed=True, description="所属分层")
    ruleType: RiskRuleTypeEnum | None = Body(None, embed=True, description="触发的规则类型")
    title: str = Body(..., embed=True, description="事件标题")
    description: str = Body("", embed=True, description="事件描述")
    symbol: str | None = Body(None, embed=True, description="关联交易对")
    actionTaken: str | None = Body(None, embed=True, description="采取的处置动作")
