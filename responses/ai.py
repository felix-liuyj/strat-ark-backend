"""AI 投研响应数据模型。"""

from datetime import datetime

from pydantic import Field

from libs.schema import ApiResponseModel
from models.ai import AgentReportTypeEnum

__all__ = (
    "AgentOpinionData",
    "AgentReportData",
    "AgentReportSummaryData",
)


class AgentOpinionData(ApiResponseModel):
    """单个 Agent 观点（八类 Agent 之一）。"""

    role: str = Field(..., description="Agent 角色")
    name: str = Field(..., description="Agent 名称")
    stance: str = Field(..., description="立场")
    summary: str = Field(..., description="观点摘要")
    points: list[str] = Field(default_factory=list, description="要点列表")


class AgentReportSummaryData(ApiResponseModel):
    """报告摘要（历史报告列表行）。"""

    id: int = Field(..., description="报告 ID")
    reportType: AgentReportTypeEnum = Field(..., description="报告类型")
    symbol: str = Field(..., description="交易对")
    timeframe: str = Field(..., description="周期")
    signal: str | None = Field(None, description="综合信号")
    confidence: float = Field(..., description="置信度（0-1）")
    riskLevel: str | None = Field(None, description="风险等级")
    createdAt: datetime = Field(..., description="生成时间")


class AgentReportData(ApiResponseModel):
    """报告详情（结构化结论 + 八类 Agent 观点）。"""

    id: int = Field(..., description="报告 ID")
    reportType: AgentReportTypeEnum = Field(..., description="报告类型")
    symbol: str = Field(..., description="交易对")
    timeframe: str = Field(..., description="周期")
    marketState: str | None = Field(None, description="市场状态")
    signal: str | None = Field(None, description="综合信号")
    confidence: float = Field(..., description="置信度（0-1）")
    riskLevel: str | None = Field(None, description="风险等级")
    entryZone: list[float] = Field(default_factory=list, description="入场区间")
    stopLoss: float | None = Field(None, description="止损价")
    takeProfit: list[float] = Field(default_factory=list, description="止盈价位")
    bullScore: int | None = Field(None, description="多头分值")
    bearScore: int | None = Field(None, description="空头分值")
    summary: str = Field(..., description="综合摘要")
    agents: list[AgentOpinionData] = Field(default_factory=list, description="八类 Agent 观点")
    signalId: int | None = Field(None, description="关联信号 ID")
    backtestTaskId: int | None = Field(None, description="关联回测任务 ID")
    createdAt: datetime = Field(..., description="生成时间")
