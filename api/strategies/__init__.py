"""策略 API 路由（RESTful，资源级动作 /strategies/{id}/{action}）。"""

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.strategy import StrategyCreateForm, StrategyImportForm, StrategyUpdateForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.strategy import (
    StrategyBacktestSubmitResponseData,
    StrategyDetailResponseData,
    StrategyListItemResponseData,
)
from view_models.strategies import (
    CreateStrategyViewModel,
    GetStrategyDetailViewModel,
    ImportStrategyViewModel,
    ListStrategiesViewModel,
    SubmitStrategyBacktestViewModel,
    UpdateStrategyViewModel,
)

__all__ = ("router",)

router = APIRouter()

_TAGS = ["StratArk/策略"]


@router.get(
    "/strategies",
    response_model=BaseResponseModel[list[StrategyListItemResponseData]],
    summary="策略列表",
    description="返回平台内置策略与当前用户私有策略，内置策略优先。",
    tags=_TAGS,
)
async def list_strategies(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListStrategiesViewModel, request, db, checker=checker)


@router.post(
    "/strategies",
    response_model=BaseResponseModel[StrategyDetailResponseData],
    summary="新建策略",
    description="创建用户私有策略并生成初始 v1.0 版本记录与源码占位。",
    tags=_TAGS,
)
async def create_strategy(
    request: Request,
    form: StrategyCreateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateStrategyViewModel, request, db, checker=checker, form=form)


@router.post(
    "/strategies/import",
    response_model=BaseResponseModel[StrategyDetailResponseData],
    summary="导入策略",
    description="导入 Freqtrade 策略源码（.py 文本），保存源码并生成初始版本。",
    tags=_TAGS,
)
async def import_strategy(
    request: Request,
    form: StrategyImportForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ImportStrategyViewModel, request, db, checker=checker, form=form)


@router.get(
    "/strategies/{strategy_id}",
    response_model=BaseResponseModel[StrategyDetailResponseData],
    summary="策略详情",
    description="返回单个策略的指标、参数、风险标签、源码预览与版本记录。",
    tags=_TAGS,
)
async def get_strategy_detail(
    request: Request,
    strategy_id: int = Path(..., description="策略 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        GetStrategyDetailViewModel, request, db, checker=checker, strategy_id=strategy_id
    )


@router.put(
    "/strategies/{strategy_id}",
    response_model=BaseResponseModel[StrategyDetailResponseData],
    summary="更新策略参数",
    description="更新用户私有策略的名称、周期、参数；内置策略只读不可修改。",
    tags=_TAGS,
)
async def update_strategy(
    request: Request,
    form: StrategyUpdateForm,
    strategy_id: int = Path(..., description="策略 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        UpdateStrategyViewModel, request, db, checker=checker, form=form, strategy_id=strategy_id
    )


@router.post(
    "/strategies/{strategy_id}/backtest",
    response_model=BaseResponseModel[StrategyBacktestSubmitResponseData],
    summary="提交回测",
    description="提交策略回测入口（占位回执），真实回测任务在 backtests 域执行。",
    tags=_TAGS,
)
async def submit_strategy_backtest(
    request: Request,
    strategy_id: int = Path(..., description="策略 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        SubmitStrategyBacktestViewModel, request, db, checker=checker, strategy_id=strategy_id
    )
