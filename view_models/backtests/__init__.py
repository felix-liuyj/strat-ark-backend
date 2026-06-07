"""回测中心 ViewModel。"""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.backtests import BacktestCreateForm
from libs.auth.permissions import PermissionChecker
from libs.integrations import backtest_engine, trading_agents
from models.backtests import BacktestStatusEnum, BacktestTask
from responses.backtests import (
    AgentOpinionData,
    BacktestAiReviewData,
    BacktestDetailData,
    BacktestMetricsData,
    BacktestSeriesData,
    BacktestTaskData,
    DailyReturnPointData,
    DrawdownPointData,
    EquityPointData,
    PairReturnData,
)
from view_models import BaseViewModel

__all__ = (
    "CreateBacktestViewModel",
    "GetBacktestViewModel",
    "ListBacktestsViewModel",
    "ReviewBacktestViewModel",
)


def _build_task_summary(task: BacktestTask) -> BacktestTaskData:
    return BacktestTaskData(
        id=task.id,
        strategyName=task.strategy_name,
        symbol=task.symbol,
        timeframe=task.timeframe,
        startDate=task.start_date,
        endDate=task.end_date,
        status=BacktestStatusEnum(task.status),
        totalReturn=task.total_return,
        maxDrawdown=task.max_drawdown,
        sharpe=task.sharpe,
    )


def _build_metrics(task: BacktestTask) -> BacktestMetricsData | None:
    if task.total_return is None:
        return None
    return BacktestMetricsData(
        totalReturn=task.total_return,
        cagr=task.cagr or 0.0,
        maxDrawdown=task.max_drawdown or 0.0,
        sharpe=task.sharpe or 0.0,
        winRate=task.win_rate or 0.0,
        profitFactor=task.profit_factor or 0.0,
        avgDurationHours=task.avg_duration_hours or 0.0,
        trades=task.trades or 0,
        bestPair=task.best_pair or "",
        worstPair=task.worst_pair or "",
        finalBalance=task.final_balance or 0.0,
    )


def _build_series(task: BacktestTask) -> BacktestSeriesData | None:
    series = task.result_series or {}
    if not series:
        return None
    return BacktestSeriesData(
        equityCurve=[EquityPointData(**p) for p in series.get("equityCurve", [])],
        drawdownCurve=[DrawdownPointData(**p) for p in series.get("drawdownCurve", [])],
        dailyReturns=[DailyReturnPointData(**p) for p in series.get("dailyReturns", [])],
        pairReturns=[PairReturnData(**p) for p in series.get("pairReturns", [])],
    )


def _build_ai_review(task: BacktestTask) -> BacktestAiReviewData | None:
    review = task.ai_review
    if not review:
        return None
    return BacktestAiReviewData(
        verdict=review["verdict"],
        strength=review["strength"],
        weakness=review["weakness"],
        suggestion=review["suggestion"],
        summary=review["summary"],
        agents=[AgentOpinionData(**a) for a in review.get("agents", [])],
    )


def _build_detail(task: BacktestTask) -> BacktestDetailData:
    return BacktestDetailData(
        task=_build_task_summary(task),
        metrics=_build_metrics(task),
        series=_build_series(task),
        aiReview=_build_ai_review(task),
    )


def _serialize_series(result: backtest_engine.BacktestRunResult) -> dict:
    """将引擎产出的各序列转为可 JSON 落库的字典。"""
    return {
        "equityCurve": [{"x": p.x, "value": p.value} for p in result.equity_curve],
        "drawdownCurve": [{"x": p.x, "value": p.value} for p in result.drawdown_curve],
        "dailyReturns": [{"day": p.day, "value": p.value} for p in result.daily_returns],
        "pairReturns": [{"name": p.name, "value": p.value} for p in result.pair_returns],
    }


class CreateBacktestViewModel(BaseViewModel):
    """创建并运行回测任务（同步调引擎 stub，完成后回填结果）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: BacktestCreateForm,
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
        strategy_name = self.form.strategyName.strip()
        if not symbol or not strategy_name:
            self.illegal_parameters("策略名称与交易对不能为空")
            return
        if self.form.initialBalance <= 0:
            self.illegal_parameters("初始资金必须大于 0")
            return

        task = BacktestTask(
            user_id=int(self.checker.user_id),
            strategy_id=self.form.strategyId,
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=self.form.timeframe.strip() or "1h",
            start_date=self.form.startDate.strip(),
            end_date=self.form.endDate.strip(),
            initial_balance=self.form.initialBalance,
            fee_rate=self.form.feeRate,
            slippage_rate=self.form.slippageRate,
            status=BacktestStatusEnum.RUNNING,
        )

        # 引擎 stub 同步返回拟真结果，直接回填并标记完成（真实实现应转后台任务）。
        result = backtest_engine.run_backtest(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=task.timeframe,
            start_date=task.start_date,
            end_date=task.end_date,
            initial_balance=task.initial_balance,
            fee_rate=task.fee_rate,
            slippage_rate=task.slippage_rate,
        )
        task.total_return = result.total_return
        task.cagr = result.cagr
        task.max_drawdown = result.max_drawdown
        task.sharpe = result.sharpe
        task.win_rate = result.win_rate
        task.profit_factor = result.profit_factor
        task.avg_duration_hours = result.avg_duration_hours
        task.trades = result.trades
        task.best_pair = result.best_pair
        task.worst_pair = result.worst_pair
        task.final_balance = result.final_balance
        task.result_series = _serialize_series(result)
        task.status = BacktestStatusEnum.COMPLETED

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        self.operating_successfully(_build_detail(task))


class ListBacktestsViewModel(BaseViewModel):
    """当前用户的回测任务列表（按创建时间倒序）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        tasks = (
            await self.db.scalars(
                select(BacktestTask)
                .where(BacktestTask.user_id == int(self.checker.user_id))
                .order_by(BacktestTask.created_at.desc())
            )
        ).all()
        self.operating_successfully([_build_task_summary(t) for t in tasks])


class GetBacktestViewModel(BaseViewModel):
    """回测任务详情（指标 + 序列 + AI 复盘）。"""

    def __init__(self, request: Request, db: AsyncSession, task_id: int, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.task_id = task_id
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        task = await self.db.get(BacktestTask, self.task_id)
        if task is None or task.user_id != int(self.checker.user_id):
            self.not_found("回测任务不存在")
            return

        self.operating_successfully(_build_detail(task))


class ReviewBacktestViewModel(BaseViewModel):
    """对回测结果发起 AI 多智能体复盘（调 TradingAgents stub）。"""

    def __init__(self, request: Request, db: AsyncSession, task_id: int, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.task_id = task_id
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        task = await self.db.get(BacktestTask, self.task_id)
        if task is None or task.user_id != int(self.checker.user_id):
            self.not_found("回测任务不存在")
            return
        if task.status != BacktestStatusEnum.COMPLETED or task.total_return is None:
            self.illegal_parameters("回测尚未完成，无法复盘")
            return

        review = trading_agents.review_backtest(
            strategy_name=task.strategy_name,
            symbol=task.symbol,
            total_return=task.total_return,
            max_drawdown=task.max_drawdown or 0.0,
            sharpe=task.sharpe or 0.0,
        )
        task.ai_review = {
            "verdict": review.verdict,
            "strength": review.strength,
            "weakness": review.weakness,
            "suggestion": review.suggestion,
            "summary": review.summary,
            "agents": [
                {
                    "role": a.role.value,
                    "name": a.name,
                    "stance": a.stance,
                    "summary": a.summary,
                    "points": a.points,
                }
                for a in review.agents
            ],
        }
        await self.db.commit()
        await self.db.refresh(task)

        self.operating_successfully(_build_detail(task))
