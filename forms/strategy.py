"""策略请求表单（camelCase Body）。"""

from fastapi import Body

from libs.schema import ApiFormModel
from models.strategy import StrategyTypeEnum

__all__ = (
    "StrategyCreateForm",
    "StrategyImportForm",
    "StrategyUpdateForm",
)


class StrategyCreateForm(ApiFormModel):
    name: str = Body(..., embed=True, description="策略名称，例如 My Trend V1")
    description: str | None = Body(None, embed=True, description="策略描述")
    strategyType: StrategyTypeEnum = Body(
        ..., embed=True, description="类型：trend / mean_reversion / breakout / ai_assisted / risk_guard"
    )
    timeframe: str = Body("15m", embed=True, description="周期，例如 15m / 1h / 4h")
    market: str | None = Body(None, embed=True, description="适用市场描述")
    params: list[list[str]] | None = Body(None, embed=True, description="有序参数键值对列表")


class StrategyUpdateForm(ApiFormModel):
    name: str | None = Body(None, embed=True, description="策略名称")
    description: str | None = Body(None, embed=True, description="策略描述")
    timeframe: str | None = Body(None, embed=True, description="周期")
    market: str | None = Body(None, embed=True, description="适用市场描述")
    params: list[list[str]] | None = Body(None, embed=True, description="有序参数键值对列表")


class StrategyImportForm(ApiFormModel):
    name: str = Body(..., embed=True, description="策略名称")
    sourceCode: str = Body(..., embed=True, description="Freqtrade 策略源码（.py 文本）")
    strategyType: StrategyTypeEnum = Body(StrategyTypeEnum.TREND, embed=True, description="类型")
    timeframe: str = Body("15m", embed=True, description="周期")
