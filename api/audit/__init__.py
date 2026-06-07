"""审计日志 API 路由（管理员专属）。"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.audit import AuditExportForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.audit import (
    AuditChainVerifyResponseData,
    AuditEntryResponseData,
    AuditExportResponseData,
    AuditKpiResponseData,
    AuditListResponseData,
)
from view_models.audit import (
    ExportAuditLogsViewModel,
    GetAuditEntryViewModel,
    GetAuditKpiViewModel,
    ListAuditLogsViewModel,
    VerifyAuditChainViewModel,
)

__all__ = ("router",)

router = APIRouter()

_TAGS = ["StratArk/审计日志"]


@router.get(
    "/audit-logs",
    response_model=BaseResponseModel[AuditListResponseData],
    summary="获取审计日志列表",
    description="仅管理员可访问。分页返回审计日志，支持类别 / 角色 / 时间筛选。",
    tags=_TAGS,
)
async def list_audit_logs(
    request: Request,
    category: str | None = Query(None, description="类别筛选"),
    role: str | None = Query(None, description="操作者角色筛选"),
    start_time: str | None = Query(None, description="起始时间 ISO 8601"),
    end_time: str | None = Query(None, description="结束时间 ISO 8601"),
    page_no: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        ListAuditLogsViewModel,
        request,
        db,
        checker=checker,
        category=category,
        role=role,
        start_time=start_time,
        end_time=end_time,
        page_no=page_no,
        page_size=page_size,
    )


@router.get(
    "/audit-logs/kpi",
    response_model=BaseResponseModel[AuditKpiResponseData],
    summary="获取审计 KPI",
    description="仅管理员可访问。返回审计 KPI 统计（总数 / 成功 / 拦截 / 角色 / 各类别计数）。",
    tags=_TAGS,
)
async def get_audit_kpi(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetAuditKpiViewModel, request, db, checker=checker)


@router.get(
    "/audit-logs/verify-chain",
    response_model=BaseResponseModel[AuditChainVerifyResponseData],
    summary="校验审计哈希链",
    description="仅管理员可访问。按序重算每条签名并与存储值比对，验证链路完整性。",
    tags=_TAGS,
)
async def verify_audit_chain(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(VerifyAuditChainViewModel, request, db, checker=checker)


@router.post(
    "/audit-logs/export",
    response_model=BaseResponseModel[AuditExportResponseData],
    summary="导出审计日志",
    description="仅管理员可访问。按筛选条件导出审计日志记录内容。",
    tags=_TAGS,
)
async def export_audit_logs(
    request: Request,
    form: AuditExportForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ExportAuditLogsViewModel, request, db, checker=checker, form=form)


@router.get(
    "/audit-logs/{entry_id}",
    response_model=BaseResponseModel[AuditEntryResponseData],
    summary="获取审计详情",
    description="仅管理员可访问。返回单条审计记录的完整信息（含 details 与链式签名）。",
    tags=_TAGS,
)
async def get_audit_entry(
    request: Request,
    entry_id: int,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetAuditEntryViewModel, request, db, checker=checker, entry_id=entry_id)
