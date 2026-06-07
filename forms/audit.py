"""审计日志请求表单（管理员专属）。

审计日志为 append-only，无创建 / 更新 / 删除表单；仅提供导出筛选表单，
列表与详情、链校验的筛选条件走 Query / Path。
"""

from fastapi import Body

from libs.schema import ApiFormModel
from models.audit_log import ActorTypeEnum, AuditCategoryEnum

__all__ = ("AuditExportForm",)


class AuditExportForm(ApiFormModel):
    """导出审计日志的筛选条件（与列表筛选一致）。"""

    category: AuditCategoryEnum | None = Body(None, embed=True, description="类别筛选")
    role: ActorTypeEnum | None = Body(None, embed=True, description="操作者角色筛选")
    startTime: str | None = Body(None, embed=True, description="起始时间（ISO 8601）")
    endTime: str | None = Body(None, embed=True, description="结束时间（ISO 8601）")
