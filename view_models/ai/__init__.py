"""AI 投研 ViewModel（agent_reports）。

调 TradingAgents 多智能体 stub 产出结构化研报并落库；八类 Agent 协作。
AI 仅产出辅助决策结论，不直接下单。
"""

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.ai import BacktestReviewForm, MarketAnalysisForm, SignalReviewForm
from libs.auth.permissions import PermissionChecker
from libs.integrations import trading_agents
from models.ai import AgentReport, AgentReportTypeEnum
from models.backtests import BacktestStatusEnum, BacktestTask
from models.signals import Signal
from responses.ai import AgentOpinionData, AgentReportData, AgentReportSummaryData
from view_models.common.base import BaseViewModel

__all__ = (
    "AnalyzeMarketViewModel",
    "GetReportViewModel",
    "ListReportsViewModel",
    "ReviewBacktestReportViewModel",
    "ReviewSignalViewModel",
)


def _serialize_agents(agents: list[trading_agents.AgentOpinion]) -> list[dict[str, Any]]:
    return [
        {
            "role": a.role.value,
            "name": a.name,
            "stance": a.stance,
            "summary": a.summary,
            "points": a.points,
        }
        for a in agents
    ]


def _build_summary(report: AgentReport) -> AgentReportSummaryData:
    return AgentReportSummaryData(
        id=report.id,
        reportType=AgentReportTypeEnum(report.report_type),
        symbol=report.symbol,
        timeframe=report.timeframe,
        signal=report.signal,
        confidence=report.confidence,
        riskLevel=report.risk_level,
        createdAt=report.created_at,
    )


def _build_report(report: AgentReport) -> AgentReportData:
    structured = report.structured or {}
    return AgentReportData(
        id=report.id,
        reportType=AgentReportTypeEnum(report.report_type),
        symbol=report.symbol,
        timeframe=report.timeframe,
        marketState=report.market_state,
        signal=report.signal,
        confidence=report.confidence,
        riskLevel=report.risk_level,
        entryZone=structured.get("entryZone", []),
        stopLoss=structured.get("stopLoss"),
        takeProfit=structured.get("takeProfit", []),
        bullScore=structured.get("bullScore"),
        bearScore=structured.get("bearScore"),
        summary=report.summary,
        agents=[AgentOpinionData(**a) for a in (report.agents or [])],
        signalId=report.signal_id,
        backtestTaskId=report.backtest_task_id,
        createdAt=report.created_at,
    )


class AnalyzeMarketViewModel(BaseViewModel):
    """市场分析：调多智能体 stub 输出结构化报告并落库。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: MarketAnalysisForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        symbol = self.form.symbol.strip()
        if not symbol:
            self.illegal_parameters("交易对不能为空")
            return

        result = await trading_agents.run_market_analysis(symbol=symbol, timeframe=self.form.timeframe.strip() or "1h")
        report = AgentReport(
            user_id=int(self.checker.user_id),
            report_type=AgentReportTypeEnum.MARKET_ANALYSIS,
            symbol=result.symbol,
            timeframe=result.timeframe,
            market_state=result.market_state,
            signal=result.signal,
            confidence=result.confidence,
            risk_level=result.risk_level,
            summary=result.summary,
            structured={
                "entryZone": result.entry_zone,
                "stopLoss": result.stop_loss,
                "takeProfit": result.take_profit,
                "bullScore": result.bull_score,
                "bearScore": result.bear_score,
            },
            agents=_serialize_agents(result.agents),
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        self.operating_successfully(_build_report(report))


class ReviewSignalViewModel(BaseViewModel):
    """信号复核：对指定信号调多智能体 stub 复核并落库。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: SignalReviewForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        signal = await self.db.get(Signal, self.form.signalId)
        if signal is None or signal.user_id != int(self.checker.user_id):
            self.not_found("信号不存在")
            return

        result = await trading_agents.review_signal(
            symbol=signal.symbol,
            direction=signal.direction,
            confidence=signal.confidence,
            risk_level=signal.risk_level,
        )
        report = AgentReport(
            user_id=int(self.checker.user_id),
            report_type=AgentReportTypeEnum.SIGNAL_REVIEW,
            symbol=signal.symbol,
            timeframe="-",
            signal=result.recommendation,
            confidence=result.confidence,
            risk_level=result.risk_level,
            summary=result.summary,
            structured={},
            agents=_serialize_agents(result.agents),
            signal_id=signal.id,
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        self.operating_successfully(_build_report(report))


class ReviewBacktestReportViewModel(BaseViewModel):
    """回测复盘：对指定回测任务调多智能体 stub 复盘并落库。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: BacktestReviewForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        task = await self.db.get(BacktestTask, self.form.backtestTaskId)
        if task is None or task.user_id != int(self.checker.user_id):
            self.not_found("回测任务不存在")
            return
        if task.status != BacktestStatusEnum.COMPLETED or task.total_return is None:
            self.illegal_parameters("回测尚未完成，无法复盘")
            return

        result = await trading_agents.review_backtest(
            strategy_name=task.strategy_name,
            symbol=task.symbol,
            total_return=task.total_return,
            max_drawdown=task.max_drawdown or 0.0,
            sharpe=task.sharpe or 0.0,
        )
        report = AgentReport(
            user_id=int(self.checker.user_id),
            report_type=AgentReportTypeEnum.BACKTEST_REVIEW,
            symbol=task.symbol,
            timeframe=task.timeframe,
            signal=result.verdict,
            confidence=0.0,
            risk_level=None,
            summary=result.summary,
            structured={
                "strength": result.strength,
                "weakness": result.weakness,
                "suggestion": result.suggestion,
            },
            agents=_serialize_agents(result.agents),
            backtest_task_id=task.id,
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        self.operating_successfully(_build_report(report))


class ListReportsViewModel(BaseViewModel):
    """历史报告列表，支持按类型筛选（按生成时间倒序）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        report_type: str | None = None,
    ) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db
        self.report_type = report_type

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        statement = select(AgentReport).where(AgentReport.user_id == int(self.checker.user_id))
        if self.report_type:
            statement = statement.where(AgentReport.report_type == self.report_type)
        statement = statement.order_by(AgentReport.created_at.desc())

        reports = (await self.db.scalars(statement)).all()
        self.operating_successfully([_build_summary(r) for r in reports])


class GetReportViewModel(BaseViewModel):
    """报告详情（结构化结论 + 八类 Agent 观点）。"""

    def __init__(self, request: Request, db: AsyncSession, report_id: int, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.report_id = report_id
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        report = await self.db.get(AgentReport, self.report_id)
        if report is None or report.user_id != int(self.checker.user_id):
            self.not_found("报告不存在")
            return

        self.operating_successfully(_build_report(report))
