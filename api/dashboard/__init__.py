"""Dashboard API 路由。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.dashboard import DashboardOverviewResponseData
from view_models.dashboard import GetDashboardOverviewViewModel

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/dashboard/overview",
    response_model=BaseResponseModel[DashboardOverviewResponseData],
    summary="获取 Dashboard 聚合数据",
    description="返回 Dashboard 首屏所需的顶部状态、风控、KPI、AI 概要、Bot、信号与持仓聚合数据。",
    tags=["StratArk/Dashboard"],
)
async def get_dashboard_overview(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetDashboardOverviewViewModel, request, db, checker=checker)
