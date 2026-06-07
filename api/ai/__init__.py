"""AI 投研 API 路由（agent_reports）。"""

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.ai import BacktestReviewForm, MarketAnalysisForm, SignalReviewForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.ai import AgentReportData, AgentReportSummaryData
from view_models.ai import (
    AnalyzeMarketViewModel,
    GetReportViewModel,
    ListReportsViewModel,
    ReviewBacktestReportViewModel,
    ReviewSignalViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.post(
    "/ai/market-analysis",
    response_model=BaseResponseModel[AgentReportData],
    summary="市场分析",
    description="输入交易对与周期，调 TradingAgents 八类 Agent 协作输出结构化研报并落库。",
    tags=["StratArk/AI 投研"],
)
async def analyze_market(
    request: Request,
    form: MarketAnalysisForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(AnalyzeMarketViewModel, request, db, checker=checker, form=form)


@router.post(
    "/ai/signal-review",
    response_model=BaseResponseModel[AgentReportData],
    summary="信号复核",
    description="对指定信号发起多智能体复核，输出批准/复核建议与各 Agent 观点。",
    tags=["StratArk/AI 投研"],
)
async def review_signal(
    request: Request,
    form: SignalReviewForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ReviewSignalViewModel, request, db, checker=checker, form=form)


@router.post(
    "/ai/backtest-review",
    response_model=BaseResponseModel[AgentReportData],
    summary="回测复盘",
    description="对已完成的回测任务发起多智能体复盘，输出归因与改进建议。",
    tags=["StratArk/AI 投研"],
)
async def review_backtest(
    request: Request,
    form: BacktestReviewForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ReviewBacktestReportViewModel, request, db, checker=checker, form=form)


@router.get(
    "/ai/reports",
    response_model=BaseResponseModel[list[AgentReportSummaryData]],
    summary="报告列表",
    description="返回当前用户的 AI 投研报告摘要，支持按报告类型筛选，按生成时间倒序。",
    tags=["StratArk/AI 投研"],
)
async def list_reports(
    request: Request,
    report_type: str | None = Query(None, description="按报告类型筛选"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListReportsViewModel, request, db, checker=checker, report_type=report_type)


@router.get(
    "/ai/reports/{report_id}",
    response_model=BaseResponseModel[AgentReportData],
    summary="报告详情",
    description="返回指定 AI 投研报告的结构化结论与八类 Agent 观点。",
    tags=["StratArk/AI 投研"],
)
async def get_report(
    request: Request,
    report_id: int = Path(..., description="报告 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetReportViewModel, request, db, report_id=report_id, checker=checker)
