"""Health check API."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.common.health import StatusResponseData
from view_models.common.health import QueryHealthStatusViewModel

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/health",
    response_model=BaseResponseModel[StatusResponseData],
    summary="服务健康检查",
    description="检查服务、数据库和 Redis 的连接状态。",
    tags=["StratArk/健康检查"],
)
async def get_health(request: Request, db: AsyncSession = Depends(get_db)) -> BaseResponseModel:
    return await create_response(QueryHealthStatusViewModel, request, db)
