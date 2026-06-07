"""信号中心请求表单。"""

from fastapi import Body

from libs.schema import ApiFormModel
from models.signals import SignalDirectionEnum, SignalRiskLevelEnum

__all__ = ("SignalCreateForm",)


class SignalCreateForm(ApiFormModel):
    """手动创建交易信号（交易对 / 方向 / 入场 / 止损 / 止盈 / 置信度 / 风险）。"""

    symbol: str = Body(..., embed=True, description="交易对，如 BTC/USDT")
    direction: SignalDirectionEnum = Body(..., embed=True, description="方向：long / short / neutral")
    entryPrice: float | None = Body(None, embed=True, description="入场价")
    stopLoss: float | None = Body(None, embed=True, description="止损价")
    takeProfit: float | None = Body(None, embed=True, description="止盈价")
    confidence: float = Body(0.5, embed=True, description="置信度（0-1 小数）")
    riskLevel: SignalRiskLevelEnum = Body(SignalRiskLevelEnum.MEDIUM, embed=True, description="风险等级")
    note: str | None = Body(None, embed=True, description="备注")
