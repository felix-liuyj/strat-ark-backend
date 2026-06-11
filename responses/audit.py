"""审计日志响应模型（管理员专属）。"""

from datetime import datetime
from typing import Any

from pydantic import Field

from libs.response import BasePaginationResponseDataType
from libs.schema import ApiResponseModel

__all__ = (
    "AuditChainVerifyResponseData",
    "AuditEntryResponseData",
    "AuditExportResponseData",
    "AuditKpiResponseData",
    "AuditListResponseData",
)


class AuditEntryResponseData(ApiResponseModel):
    """单条审计记录（含 details 与链式签名，供可展开行使用）。"""

    id: int = Field(..., description="审计记录 ID")
    actor: str = Field(..., description="操作者名称")
    actorId: str | None = Field(None, description="操作者 ID")
    actorType: str = Field(..., description="操作者类型 admin / system / user")
    action: str = Field(..., description="动作")
    category: str = Field(..., description="类别")
    resource: str = Field(..., description="资源")
    resourceId: str | None = Field(None, description="资源 ID")
    message: str = Field(..., description="描述")
    details: dict[str, Any] = Field(..., description="变更 / 元数据明细")
    status: str = Field(..., description="结果 success / failed")
    errorMessage: str | None = Field(None, description="失败原因")
    endpoint: str | None = Field(None, description="请求端点")
    method: str | None = Field(None, description="请求方法")
    ipAddress: str | None = Field(None, description="来源 IP")
    userAgent: str | None = Field(None, description="User-Agent")
    prevSignature: str | None = Field(None, description="上一条签名")
    signature: str | None = Field(None, description="本条链式签名")
    createdAt: datetime = Field(..., description="发生时间")


class AuditListResponseData(BasePaginationResponseDataType[AuditEntryResponseData]):
    """审计日志分页列表。"""


class AuditKpiResponseData(ApiResponseModel):
    """审计 KPI（顶部统计卡）。"""

    total: int = Field(..., description="总记录数")
    successCount: int = Field(..., description="成功数")
    blockedCount: int = Field(..., description="拦截 / 失败数")
    adminCount: int = Field(..., description="管理员操作数")
    systemCount: int = Field(..., description="系统操作数")
    categoryCounts: dict[str, int] = Field(..., description="各类别计数")


class AuditChainVerifyResponseData(ApiResponseModel):
    """链式签名校验结果。"""

    valid: bool = Field(..., description="哈希链是否完整")
    checked: int = Field(..., description="已校验记录数")
    brokenAtId: int | None = Field(None, description="断链的记录 ID（valid=false 时）")
    message: str = Field(..., description="校验结论")


class AuditExportResponseData(ApiResponseModel):
    """审计日志导出结果。"""

    exported: int = Field(..., description="导出记录数")
    format: str = Field(..., description="导出格式")
    items: list[AuditEntryResponseData] = Field(..., description="导出的记录内容")
