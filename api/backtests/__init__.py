"""回测中心 API 路由。"""

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.backtests import BacktestCreateForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.backtests import BacktestDetailData, BacktestResultData, BacktestTaskData
from view_models.backtests import (
    CreateBacktestViewModel,
    GetBacktestResultViewModel,
    GetBacktestViewModel,
    ListBacktestsViewModel,
    ReviewBacktestViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.post(
    "/backtests",
    response_model=BaseResponseModel[BacktestDetailData],
    summary="创建回测任务",
    description="提交策略、交易对、时间范围、初始资金、手续费与滑点，运行回测并返回结果。",
    tags=["StratArk/回测中心"],
)
async def create_backtest(
    request: Request,
    form: BacktestCreateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateBacktestViewModel, request, db, checker=checker, form=form)


@router.get(
    "/backtests",
    response_model=BaseResponseModel[list[BacktestTaskData]],
    summary="回测任务列表",
    description="返回当前用户的回测任务摘要，按创建时间倒序。",
    tags=["StratArk/回测中心"],
)
async def list_backtests(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListBacktestsViewModel, request, db, checker=checker)


@router.get(
    "/backtests/{task_id}/result",
    response_model=BaseResponseModel[BacktestResultData],
    summary="回测结果",
    description="返回指定回测任务的绩效指标、权益曲线、回撤、每日收益与交易对归因。",
    tags=["StratArk/回测中心"],
)
async def get_backtest_result(
    request: Request,
    task_id: int = Path(..., description="回测任务 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetBacktestResultViewModel, request, db, task_id=task_id, checker=checker)


@router.get(
    "/backtests/{task_id}",
    response_model=BaseResponseModel[BacktestDetailData],
    summary="回测任务详情",
    description="返回指定回测任务的绩效指标、权益/回撤/每日收益/交易对序列与 AI 复盘。",
    tags=["StratArk/回测中心"],
)
async def get_backtest(
    request: Request,
    task_id: int = Path(..., description="回测任务 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetBacktestViewModel, request, db, task_id=task_id, checker=checker)


@router.post(
    "/backtests/{task_id}/ai-review",
    response_model=BaseResponseModel[BacktestDetailData],
    summary="回测 AI 复盘",
    description="对已完成的回测任务发起 TradingAgents 多智能体复盘，生成归因与改进建议。",
    tags=["StratArk/回测中心"],
)
async def review_backtest(
    request: Request,
    task_id: int = Path(..., description="回测任务 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ReviewBacktestViewModel, request, db, task_id=task_id, checker=checker)
