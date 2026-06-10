"""交易记录 API 路由（交易记录 / 持仓 / 订单 / 统计 / 导出）。"""

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.trade import CancelOrderForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.trade import (
    OpenOrderResponseData,
    PositionResponseData,
    TradeExportResponseData,
    TradeResponseData,
    TradeStatsResponseData,
)
from view_models.trades import (
    CancelOrderViewModel,
    ExportTradesViewModel,
    ListOpenOrdersViewModel,
    ListPositionsViewModel,
    ListTradesViewModel,
    TradeStatsViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/trades",
    response_model=BaseResponseModel[list[TradeResponseData]],
    summary="交易记录列表",
    description="返回交易记录，支持交易对搜索、状态筛选（all/open/closed/profit/loss）与 Bot 多选（逗号分隔）。",
    tags=["StratArk/交易记录"],
)
async def list_trades(
    request: Request,
    query: str = Query("", description="按交易对模糊搜索"),
    status_filter: str = Query("all", description="状态筛选：all/open/closed/profit/loss"),
    bots: str | None = Query(None, description="Bot 名多选，逗号分隔；为空不过滤"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        ListTradesViewModel,
        request,
        db,
        checker=checker,
        query=query,
        status_filter=status_filter,
        bots=bots,
    )


@router.get(
    "/trades/stats",
    response_model=BaseResponseModel[TradeStatsResponseData],
    summary="交易统计 KPI",
    description="返回总交易数、胜率、盈亏比与净盈亏等指标卡数据。",
    tags=["StratArk/交易记录"],
)
async def get_trade_stats(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(TradeStatsViewModel, request, db, checker=checker)


@router.get(
    "/trades/export",
    response_model=BaseResponseModel[TradeExportResponseData],
    summary="导出交易记录 CSV",
    description="返回交易记录的 CSV 文本与建议文件名，由前端触发下载。",
    tags=["StratArk/交易记录"],
)
async def export_trades(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ExportTradesViewModel, request, db, checker=checker)


@router.get(
    "/positions",
    response_model=BaseResponseModel[list[PositionResponseData]],
    summary="持仓列表",
    description="返回当前持仓：开仓价、当前价、数量、持仓价值与未实现盈亏。",
    tags=["StratArk/交易记录"],
)
async def list_positions(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListPositionsViewModel, request, db, checker=checker)


@router.get(
    "/orders",
    response_model=BaseResponseModel[list[OpenOrderResponseData]],
    summary="未完成订单列表",
    description="返回未完成的挂单（pending / partial）。",
    tags=["StratArk/交易记录"],
)
async def list_open_orders(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListOpenOrdersViewModel, request, db, checker=checker)


@router.post(
    "/orders/{order_id}/cancel",
    response_model=BaseResponseModel[None],
    summary="取消未完成订单",
    description="按订单引用号取消挂单，可附带取消原因。",
    tags=["StratArk/交易记录"],
)
async def cancel_order(
    request: Request,
    form: CancelOrderForm,
    order_id: str = Path(..., description="订单引用号"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CancelOrderViewModel, request, db, checker=checker, order_id=order_id)
