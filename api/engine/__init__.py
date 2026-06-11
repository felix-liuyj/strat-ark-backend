"""引擎管理 API 路由（管理员专属）。"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.engine import (
    EngineConnectionUpdateForm,
    EngineDeploymentUpdateForm,
    EngineOpExecuteForm,
)
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from models.engine import EngineKindEnum
from responses.engine import (
    EngineConnectionResponseData,
    EngineDeploymentResponseData,
    EngineMonitorResponseData,
    EngineOpResponseData,
    EngineResponseData,
)
from view_models.engine import (
    ExecuteEngineOpViewModel,
    GetEngineConnectionViewModel,
    GetEngineDeploymentViewModel,
    GetEngineMonitorViewModel,
    ListEngineOpsViewModel,
    ListEnginesViewModel,
    UpdateEngineConnectionViewModel,
    UpdateEngineDeploymentViewModel,
)

__all__ = ("router",)

router = APIRouter()

_TAGS = ["StratArk/引擎管理"]


@router.get(
    "/engines",
    response_model=BaseResponseModel[list[EngineResponseData]],
    summary="获取引擎列表",
    description="仅管理员可访问。返回 Freqtrade / TradingAgents 两套引擎的摘要状态。",
    tags=_TAGS,
)
async def list_engines(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListEnginesViewModel, request, db, checker=checker)


@router.get(
    "/engines/{engine_kind}/monitor",
    response_model=BaseResponseModel[EngineMonitorResponseData],
    summary="获取引擎监控",
    description="仅管理员可访问。返回指定引擎的服务连接状态、真实指标、依赖与日志集合；实例不可达时返回空集合或空值。",
    tags=_TAGS,
)
async def get_engine_monitor(
    request: Request,
    engine_kind: EngineKindEnum,
    log_level: str | None = Query(None, description="日志级别筛选"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        GetEngineMonitorViewModel,
        request,
        db,
        checker=checker,
        engine_kind=engine_kind,
        log_level=log_level,
    )


@router.get(
    "/engines/{engine_kind}/connection",
    response_model=BaseResponseModel[EngineConnectionResponseData],
    summary="获取连接配置",
    description="仅管理员可访问。返回指定引擎的连接配置，敏感凭证已掩码。",
    tags=_TAGS,
)
async def get_engine_connection(
    request: Request,
    engine_kind: EngineKindEnum,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        GetEngineConnectionViewModel, request, db, checker=checker, engine_kind=engine_kind
    )


@router.put(
    "/engines/{engine_kind}/connection",
    response_model=BaseResponseModel[EngineConnectionResponseData],
    summary="更新连接配置",
    description="仅管理员可访问。更新指定引擎的连接配置，掩码占位字段不会覆盖已存凭证。",
    tags=_TAGS,
)
async def update_engine_connection(
    request: Request,
    engine_kind: EngineKindEnum,
    form: EngineConnectionUpdateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        UpdateEngineConnectionViewModel, request, db, checker=checker, engine_kind=engine_kind, form=form
    )


@router.get(
    "/engines/{engine_kind}/deployment",
    response_model=BaseResponseModel[EngineDeploymentResponseData],
    summary="获取部署配置",
    description="仅管理员可访问。返回指定引擎的部署配置（镜像 / 副本 / 资源 / HPA 等）。",
    tags=_TAGS,
)
async def get_engine_deployment(
    request: Request,
    engine_kind: EngineKindEnum,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        GetEngineDeploymentViewModel, request, db, checker=checker, engine_kind=engine_kind
    )


@router.put(
    "/engines/{engine_kind}/deployment",
    response_model=BaseResponseModel[EngineDeploymentResponseData],
    summary="更新部署配置",
    description="仅管理员可访问。更新指定引擎的部署配置，可同步期望副本数。",
    tags=_TAGS,
)
async def update_engine_deployment(
    request: Request,
    engine_kind: EngineKindEnum,
    form: EngineDeploymentUpdateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        UpdateEngineDeploymentViewModel, request, db, checker=checker, engine_kind=engine_kind, form=form
    )


@router.post(
    "/engines/{engine_kind}/operations",
    response_model=BaseResponseModel[EngineOpResponseData],
    summary="执行运维操作",
    description=(
        "仅管理员可访问。执行 scale / restart / reload / drain / clear-queue / redeploy / "
        "紧急停机 / 销毁重建，记录到 engine_ops；危险操作同时写平台审计日志。"
    ),
    tags=_TAGS,
)
async def execute_engine_op(
    request: Request,
    engine_kind: EngineKindEnum,
    form: EngineOpExecuteForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        ExecuteEngineOpViewModel, request, db, checker=checker, engine_kind=engine_kind, form=form
    )


@router.get(
    "/engine-ops",
    response_model=BaseResponseModel[list[EngineOpResponseData]],
    summary="获取运维流水",
    description="仅管理员可访问。返回引擎运维操作流水，可按引擎类型筛选。",
    tags=_TAGS,
)
async def list_engine_ops(
    request: Request,
    engine_kind: EngineKindEnum | None = Query(None, description="引擎类型筛选"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        ListEngineOpsViewModel, request, db, checker=checker, engine_kind=engine_kind
    )
