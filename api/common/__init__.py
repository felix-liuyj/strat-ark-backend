"""Common API routers."""

from fastapi import APIRouter

from api.common.health import router as health_router
from api.common.oss import router as oss_router

__all__ = ("common_router",)

common_router = APIRouter()
common_router.include_router(health_router)
common_router.include_router(oss_router, prefix="/common")
