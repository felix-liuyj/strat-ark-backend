"""导航菜单 API 路由。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.navigation import NavigationCountsResponseData
from view_models.navigation import GetNavigationCountsViewModel

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/navigation/counts",
    response_model=BaseResponseModel[NavigationCountsResponseData],
    summary="获取导航菜单计数",
    description="返回当前用户侧边导航菜单需要展示的待处理信号、运行中机器人与未读通知数量。",
    tags=["StratArk/导航"],
)
async def get_navigation_counts(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetNavigationCountsViewModel, request, db, checker=checker)
