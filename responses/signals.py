"""信号中心响应数据模型。"""

from datetime import datetime

from pydantic import Field

from libs.schema import ApiResponseModel
from models.signals import (
    SignalDirectionEnum,
    SignalRiskLevelEnum,
    SignalSourceEnum,
    SignalStatusEnum,
)

__all__ = ("SignalData",)


class SignalData(ApiResponseModel):
    """交易信号（列表行与详情共用）。"""

    id: int = Field(..., description="信号 ID")
    symbol: str = Field(..., description="交易对")
    direction: SignalDirectionEnum = Field(..., description="方向")
    source: SignalSourceEnum = Field(..., description="来源")
    confidence: float = Field(..., description="置信度（0-1）")
    entryPrice: float | None = Field(None, description="入场价")
    stopLoss: float | None = Field(None, description="止损价")
    takeProfit: float | None = Field(None, description="止盈价")
    riskLevel: SignalRiskLevelEnum = Field(..., description="风险等级")
    status: SignalStatusEnum = Field(..., description="状态")
    note: str | None = Field(None, description="备注")
    createdAt: datetime = Field(..., description="生成时间")
