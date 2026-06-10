"""行情 API 路由（总览 / 行情列表 / 涨跌榜 / 热力图 / 详情 / 自选）。

行情只读端点不强制登录；自选交易对读写需登录。交易对含斜杠（BTC/USDT），
相关路径段使用 ``{symbol:path}`` 转换器接收完整交易对。
"""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.market import WatchlistAddForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.market import (
    MarketDetailResponseData,
    MarketOverviewResponseData,
    MarketTickerResponseData,
    TopMoversResponseData,
)
from view_models.market import (
    AddWatchlistViewModel,
    GetMarketDetailViewModel,
    ListHeatmapViewModel,
    ListTickersViewModel,
    ListWatchlistViewModel,
    MarketOverviewViewModel,
    RemoveWatchlistViewModel,
    TopMoversViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/market/overview",
    response_model=BaseResponseModel[MarketOverviewResponseData],
    summary="市场总览 KPI",
    description="返回总市值、24h 成交额、BTC 占比与恐惧贪婪指数。只读，无需登录。",
    tags=["StratArk/行情"],
)
async def get_market_overview(request: Request) -> BaseResponseModel:
    return await create_response(MarketOverviewViewModel, request)


@router.get(
    "/market/tickers",
    response_model=BaseResponseModel[list[MarketTickerResponseData]],
    summary="行情列表",
    description="返回自选行情底表，可按 market_type（all/spot/futures）过滤。只读，无需登录。",
    tags=["StratArk/行情"],
)
async def list_tickers(
    request: Request,
    market_type: str | None = Query(None, description="现货 spot / 合约 futures / all"),
) -> BaseResponseModel:
    return await create_response(ListTickersViewModel, request, market_type=market_type)


@router.get(
    "/market/movers",
    response_model=BaseResponseModel[TopMoversResponseData],
    summary="涨跌榜",
    description="返回涨幅榜与跌幅榜（各 limit 条）。只读，无需登录。",
    tags=["StratArk/行情"],
)
async def get_top_movers(
    request: Request,
    limit: int = Query(3, ge=1, le=10, description="每榜条数"),
) -> BaseResponseModel:
    return await create_response(TopMoversViewModel, request, limit=limit)


@router.get(
    "/market/heatmap",
    response_model=BaseResponseModel[list[dict[str, Any]]],
    summary="市场热力图",
    description="返回各币种 24h 涨跌幅（symbol + changePct）。只读，无需登录。",
    tags=["StratArk/行情"],
)
async def list_heatmap(request: Request) -> BaseResponseModel:
    return await create_response(ListHeatmapViewModel, request)


@router.get(
    "/market/watchlist",
    response_model=BaseResponseModel[list[MarketTickerResponseData]],
    summary="自选行情列表",
    description="返回当前用户自选交易对及其实时行情。需登录。",
    tags=["StratArk/行情"],
)
async def list_watchlist(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListWatchlistViewModel, request, db, checker=checker)


@router.post(
    "/market/watchlist",
    response_model=BaseResponseModel[None],
    summary="新增自选交易对",
    description="将指定交易对加入当前用户自选；已存在时返回无变更。需登录。",
    tags=["StratArk/行情"],
)
async def add_watchlist(
    request: Request,
    form: WatchlistAddForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(AddWatchlistViewModel, request, db, form=form, checker=checker)


@router.delete(
    "/market/watchlist/{symbol:path}",
    response_model=BaseResponseModel[None],
    summary="移除自选交易对",
    description="从当前用户自选移除指定交易对（symbol 含斜杠，如 BTC/USDT）。需登录。",
    tags=["StratArk/行情"],
)
async def remove_watchlist(
    request: Request,
    symbol: str = Path(..., description="交易对，如 BTC/USDT"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(RemoveWatchlistViewModel, request, db, symbol=symbol, checker=checker)


@router.get(
    "/market/tickers/{symbol:path}",
    response_model=BaseResponseModel[MarketDetailResponseData],
    summary="单币种详情",
    description="返回单交易对的行情、K 线、订单簿、成交流与 AI 快照（symbol 含斜杠，如 BTC/USDT；"
    "timeframe 支持 1m / 15m / 1h / 4h / 1d）。只读，无需登录。",
    tags=["StratArk/行情"],
)
async def get_market_detail(
    request: Request,
    symbol: str = Path(..., description="交易对，如 BTC/USDT"),
    timeframe: str = Query("1h", description="K 线周期：1m / 15m / 1h / 4h / 1d"),
) -> BaseResponseModel:
    return await create_response(GetMarketDetailViewModel, request, symbol=symbol, timeframe=timeframe)
