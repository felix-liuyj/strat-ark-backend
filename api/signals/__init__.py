"""信号中心 API 路由。"""

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.signals import SignalCreateForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.signals import SignalData
from view_models.signals import (
    ApproveSignalViewModel,
    CreateSignalViewModel,
    ExecuteSignalViewModel,
    GetSignalViewModel,
    ListSignalsViewModel,
    RejectSignalViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/signals",
    response_model=BaseResponseModel[list[SignalData]],
    summary="信号列表",
    description="返回当前用户的交易信号，支持按状态与来源筛选，按生成时间倒序。",
    tags=["StratArk/信号中心"],
)
async def list_signals(
    request: Request,
    status: str | None = Query(None, description="按状态筛选"),
    source: str | None = Query(None, description="按来源筛选"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListSignalsViewModel, request, db, checker=checker, status=status, source=source)


@router.post(
    "/signals",
    response_model=BaseResponseModel[SignalData],
    summary="手动创建信号",
    description="手动录入交易信号，来源标记为 manual，初始状态为 Generated。",
    tags=["StratArk/信号中心"],
)
async def create_signal(
    request: Request,
    form: SignalCreateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateSignalViewModel, request, db, checker=checker, form=form)


@router.get(
    "/signals/{signal_id}",
    response_model=BaseResponseModel[SignalData],
    summary="信号详情",
    description="返回当前用户可见的单个交易信号详情，用于前端 View 操作弹窗或详情页。",
    tags=["StratArk/信号中心"],
)
async def get_signal(
    request: Request,
    signal_id: int = Path(..., description="信号 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetSignalViewModel, request, db, signal_id=signal_id, checker=checker)


@router.post(
    "/signals/{signal_id}/approve",
    response_model=BaseResponseModel[SignalData],
    summary="批准信号",
    description="将信号状态变更为 Approved。批准不等于自动下单，仍受 Live Mode 流程与风控规则约束。",
    tags=["StratArk/信号中心"],
)
async def approve_signal(
    request: Request,
    signal_id: int = Path(..., description="信号 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ApproveSignalViewModel, request, db, signal_id=signal_id, checker=checker)


@router.post(
    "/signals/{signal_id}/reject",
    response_model=BaseResponseModel[SignalData],
    summary="拒绝信号",
    description="将信号状态变更为 Rejected，拒绝后不可被策略使用。",
    tags=["StratArk/信号中心"],
)
async def reject_signal(
    request: Request,
    signal_id: int = Path(..., description="信号 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(RejectSignalViewModel, request, db, signal_id=signal_id, checker=checker)


@router.post(
    "/signals/{signal_id}/execute",
    response_model=BaseResponseModel[SignalData],
    summary="执行信号",
    description="将已批准信号状态变更为 Executed，仅允许从 Approved 迁移。",
    tags=["StratArk/信号中心"],
)
async def execute_signal(
    request: Request,
    signal_id: int = Path(..., description="信号 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ExecuteSignalViewModel, request, db, signal_id=signal_id, checker=checker)
