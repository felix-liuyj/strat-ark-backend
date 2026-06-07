"""审计日志 view models（管理员专属，复用 AuditLogService 与 AuditLog 模型）。

覆盖：日志分页列表（类别 / 角色 / 时间筛选）、详情（含 details 与 signature）、
KPI 统计、链式签名校验、导出。审计日志为 append-only，不提供写接口。
"""

from datetime import datetime

from fastapi import Request
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.audit import AuditExportForm
from libs.audit.service import AuditLogService
from libs.auth.permissions import PermissionChecker
from models.account import UserTypeEnum
from models.audit_log import ActorTypeEnum, AuditLog, AuditStatusEnum
from responses.audit import (
    AuditChainVerifyResponseData,
    AuditEntryResponseData,
    AuditExportResponseData,
    AuditKpiResponseData,
    AuditListResponseData,
)
from view_models import BaseViewModel

__all__ = (
    "ExportAuditLogsViewModel",
    "GetAuditEntryViewModel",
    "GetAuditKpiViewModel",
    "ListAuditLogsViewModel",
    "VerifyAuditChainViewModel",
)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_entry(row: AuditLog) -> AuditEntryResponseData:
    return AuditEntryResponseData(
        id=row.id,
        actor=row.actor,
        actorId=row.actor_id,
        actorType=row.actor_type,
        action=row.action,
        category=row.category,
        resource=row.resource,
        resourceId=row.resource_id,
        message=row.message,
        details=row.details or {},
        status=row.status,
        errorMessage=row.error_message,
        endpoint=row.endpoint,
        method=row.method,
        ipAddress=row.ip_address,
        userAgent=row.user_agent,
        prevSignature=row.prev_signature,
        signature=row.signature,
        createdAt=row.created_at,
    )


def _apply_filters(
    stmt: Select,
    category: str | None,
    role: str | None,
    start: datetime | None,
    end: datetime | None,
) -> Select:
    if category:
        stmt = stmt.where(AuditLog.category == category)
    if role:
        stmt = stmt.where(AuditLog.actor_type == role)
    if start is not None:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end is not None:
        stmt = stmt.where(AuditLog.created_at <= end)
    return stmt


class _AdminAuditViewModel(BaseViewModel):
    """审计域共享基类：统一管理员校验。"""

    checker: PermissionChecker

    def _require_admin(self) -> bool:
        self.checker.require_auth()
        if self.checker.user_type != UserTypeEnum.ADMIN:
            self.forbidden("仅管理员可访问")
            return False
        return True


class ListAuditLogsViewModel(_AdminAuditViewModel):
    """审计日志分页列表（类别 / 角色 / 时间筛选）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        category: str | None,
        role: str | None,
        start_time: str | None,
        end_time: str | None,
        page_no: int,
        page_size: int,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker
        self.category = category
        self.role = role
        self.start_time = start_time
        self.end_time = end_time
        self.page_no = max(page_no, 1)
        self.page_size = min(max(page_size, 1), 200)

    async def before(self) -> None:
        if not self._require_admin():
            return
        start = _parse_time(self.start_time)
        end = _parse_time(self.end_time)

        count_stmt = _apply_filters(
            select(func.count()).select_from(AuditLog), self.category, self.role, start, end
        )
        total = int(await self.db.scalar(count_stmt) or 0)

        list_stmt = _apply_filters(select(AuditLog), self.category, self.role, start, end)
        list_stmt = (
            list_stmt.order_by(AuditLog.id.desc())
            .offset((self.page_no - 1) * self.page_size)
            .limit(self.page_size)
        )
        rows = (await self.db.scalars(list_stmt)).all()

        self.operating_successfully(
            AuditListResponseData(
                total=total,
                pageNo=self.page_no,
                pageSize=self.page_size,
                hasMore=self.page_no * self.page_size < total,
                items=[_build_entry(row) for row in rows],
            )
        )


class GetAuditEntryViewModel(_AdminAuditViewModel):
    """审计详情（含 details 与 signature）。"""

    def __init__(self, request: Request, db: AsyncSession, entry_id: int, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.entry_id = entry_id
        self.checker = checker

    async def before(self) -> None:
        if not self._require_admin():
            return
        row = await self.db.get(AuditLog, self.entry_id)
        if row is None:
            self.not_found("审计记录不存在")
            return
        self.operating_successfully(_build_entry(row))


class GetAuditKpiViewModel(_AdminAuditViewModel):
    """审计 KPI 统计（顶部卡片 + 各类别计数）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        if not self._require_admin():
            return

        total = int(await self.db.scalar(select(func.count()).select_from(AuditLog)) or 0)
        success_count = int(
            await self.db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.status == AuditStatusEnum.SUCCESS)
            )
            or 0
        )
        blocked_count = total - success_count
        admin_count = int(
            await self.db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.actor_type == ActorTypeEnum.ADMIN)
            )
            or 0
        )
        system_count = int(
            await self.db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.actor_type == ActorTypeEnum.SYSTEM)
            )
            or 0
        )

        category_rows = (
            await self.db.execute(select(AuditLog.category, func.count()).group_by(AuditLog.category))
        ).all()
        category_counts = {str(category): int(count) for category, count in category_rows}

        self.operating_successfully(
            AuditKpiResponseData(
                total=total,
                successCount=success_count,
                blockedCount=blocked_count,
                adminCount=admin_count,
                systemCount=system_count,
                categoryCounts=category_counts,
            )
        )


class VerifyAuditChainViewModel(_AdminAuditViewModel):
    """链式签名校验：按 id 升序重算每条签名并与存储值比对。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        if not self._require_admin():
            return

        rows = (await self.db.scalars(select(AuditLog).order_by(AuditLog.id.asc()))).all()
        prev = None
        checked = 0
        for row in rows:
            checked += 1
            expected = AuditLogService._compute_signature(
                prev,
                {
                    "actor": row.actor,
                    "actor_type": row.actor_type,
                    "action": row.action,
                    "category": row.category,
                    "resource": row.resource,
                    "resource_id": row.resource_id,
                    "message": row.message,
                    "status": row.status,
                    "details": row.details or {},
                },
            )
            if expected != row.signature or (row.prev_signature or None) != (prev or None):
                self.operating_successfully(
                    AuditChainVerifyResponseData(
                        valid=False,
                        checked=checked,
                        brokenAtId=row.id,
                        message=f"哈希链在记录 #{row.id} 处断裂",
                    )
                )
                return
            prev = row.signature

        self.operating_successfully(
            AuditChainVerifyResponseData(
                valid=True,
                checked=checked,
                brokenAtId=None,
                message=f"哈希链完整 · 已校验 {checked} 条记录",
            )
        )


class ExportAuditLogsViewModel(_AdminAuditViewModel):
    """导出审计日志（按筛选条件返回全量记录内容）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: AuditExportForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        if not self._require_admin():
            return
        start = _parse_time(self.form.startTime)
        end = _parse_time(self.form.endTime)
        category = str(self.form.category) if self.form.category else None
        role = str(self.form.role) if self.form.role else None

        stmt = _apply_filters(select(AuditLog), category, role, start, end).order_by(AuditLog.id.asc())
        rows = (await self.db.scalars(stmt)).all()
        items = [_build_entry(row) for row in rows]
        self.operating_successfully(
            AuditExportResponseData(exported=len(items), format="json", items=items)
        )
