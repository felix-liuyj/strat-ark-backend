"""策略 view models。

列表 / 详情 / 参数 / 版本 / 回测入口（占位）/ 源码 / 风险标签 / 创建 / 导入 / 更新。
策略可见性：平台内置（user_id 为空）对所有登录用户可见，叠加用户私有策略。
真实回测在 backtests 域，本域回测入口仅返回占位任务。
"""

import re
from typing import Any

from fastapi import Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.strategy import StrategyCreateForm, StrategyImportForm, StrategyUpdateForm
from libs.auth.permissions import PermissionChecker
from models.strategy import (
    Strategy,
    StrategyRiskEnum,
    StrategyStatusEnum,
    StrategyTypeEnum,
    StrategyVersion,
)
from responses.strategy import (
    StrategyBacktestSubmitResponseData,
    StrategyDetailResponseData,
    StrategyListItemResponseData,
    StrategyVersionResponseData,
)
from view_models import BaseViewModel

__all__ = (
    "CreateStrategyViewModel",
    "GetStrategyDetailViewModel",
    "ImportStrategyViewModel",
    "ListStrategiesViewModel",
    "SubmitStrategyBacktestViewModel",
    "UpdateStrategyViewModel",
)

_TYPE_LABELS: dict[StrategyTypeEnum, str] = {
    StrategyTypeEnum.TREND: "趋势跟踪",
    StrategyTypeEnum.MEAN_REVERSION: "均值回归",
    StrategyTypeEnum.BREAKOUT: "突破",
    StrategyTypeEnum.AI_ASSISTED: "AI 辅助",
    StrategyTypeEnum.RISK_GUARD: "风控策略",
}
_RISK_LABELS: dict[StrategyRiskEnum, str] = {
    StrategyRiskEnum.LOW: "低",
    StrategyRiskEnum.MEDIUM: "中",
    StrategyRiskEnum.HIGH: "高",
}
_STATUS_LABELS: dict[StrategyStatusEnum, str] = {
    StrategyStatusEnum.AVAILABLE: "可用",
    StrategyStatusEnum.TESTING: "测试中",
}
_DEFAULT_PARAMS: dict[StrategyTypeEnum, list[list[str]]] = {
    StrategyTypeEnum.TREND: [["EMA Fast", "21"], ["EMA Slow", "55"], ["Stoploss", "-6%"]],
    StrategyTypeEnum.MEAN_REVERSION: [["RSI Period", "14"], ["BB Period", "20"], ["Stoploss", "-4%"]],
    StrategyTypeEnum.BREAKOUT: [["Channel Period", "20"], ["ATR Period", "14"], ["Stoploss", "-9%"]],
    StrategyTypeEnum.AI_ASSISTED: [["Min Confidence", "0.65"], ["Position Size", "3%"], ["Stoploss", "-5%"]],
    StrategyTypeEnum.RISK_GUARD: [["Max Drawdown", "-10%"], ["Daily Loss", "-3%"], ["Leverage Cap", "3x"]],
}


def _build_source_stub(name: str, timeframe: str, params: list[list[str]]) -> str:
    """生成源码预览占位（复刻前端源码片段：类名去非字母、stoploss 字面量）。"""
    class_name = re.sub(r"[^A-Za-z]", "", name) or "Strategy"
    tf = timeframe.split(" ")[0].split("/")[0].strip() or "15m"
    stop_value = "-0.06"
    for key, value in params:
        if re.search(r"stop", key, re.IGNORECASE):
            stop_value = value.replace("%", "").replace("-", "-0.0")
            break
    return (
        f"# {name}\n"
        f"class {class_name}(IStrategy):\n"
        f"    timeframe = '{tf}'\n"
        f"    stoploss = {stop_value}\n"
        f"    def populate_entry_trend(self, df):\n"
        f"        # 规则化入场，由风控最终拦截\n"
        f"        return df"
    )


def _build_list_item(strategy: Strategy) -> StrategyListItemResponseData:
    return StrategyListItemResponseData(
        id=strategy.id,
        name=strategy.name,
        strategyType=strategy.strategy_type,
        typeLabel=_TYPE_LABELS.get(strategy.strategy_type, ""),
        icon=strategy.icon,
        iconColor=strategy.icon_color,
        timeframe=strategy.timeframe,
        market=strategy.market,
        risk=strategy.risk,
        riskLabel=_RISK_LABELS.get(strategy.risk, "中"),
        status=strategy.status,
        statusLabel=_STATUS_LABELS.get(strategy.status, "可用"),
        backtestReturn=strategy.backtest_return,
        maxDrawdown=strategy.max_drawdown,
        isBuiltin=strategy.is_builtin,
    )


def _build_version_data(version: StrategyVersion) -> StrategyVersionResponseData:
    return StrategyVersionResponseData(
        id=version.id,
        version=version.version,
        isCurrent=version.is_current,
        changelog=version.changelog,
        createdAt=version.created_at.strftime("%Y-%m-%d %H:%M"),
    )


def _build_detail(strategy: Strategy, versions: list[StrategyVersion]) -> StrategyDetailResponseData:
    base = _build_list_item(strategy).model_dump()
    return StrategyDetailResponseData(
        **base,
        winRate=strategy.win_rate,
        sharpe=strategy.sharpe,
        equityCurve=strategy.equity_curve,
        params=strategy.params,
        tags=strategy.tags,
        sourceCode=strategy.source_code,
        description=strategy.description,
        versions=[_build_version_data(version) for version in versions],
    )


class _AuthedStrategyViewModel(BaseViewModel):
    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def _load_visible_strategy(self, strategy_id: int) -> Strategy | None:
        """加载内置或本人私有策略，其它用户私有策略视为不可见。"""
        strategy = await self.db.get(Strategy, strategy_id)
        if strategy is None:
            return None
        if strategy.user_id is not None and strategy.user_id != int(self.checker.user_id):
            return None
        return strategy


class ListStrategiesViewModel(_AuthedStrategyViewModel):
    """策略列表（内置 + 本人私有）。"""

    async def before(self) -> None:
        self.checker.require_auth()
        statement = (
            select(Strategy)
            .where(or_(Strategy.user_id.is_(None), Strategy.user_id == int(self.checker.user_id)))
            .order_by(Strategy.is_builtin.desc(), Strategy.id.asc())
        )
        strategies = (await self.db.scalars(statement)).all()
        self.operating_successfully([_build_list_item(strategy) for strategy in strategies])


class GetStrategyDetailViewModel(_AuthedStrategyViewModel):
    """策略详情（含参数 / 标签 / 源码 / 版本记录）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        strategy_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.strategy_id = strategy_id

    async def before(self) -> None:
        self.checker.require_auth()
        strategy = await self._load_visible_strategy(self.strategy_id)
        if strategy is None:
            self.not_found("策略不存在")
            return

        versions = (
            await self.db.scalars(
                select(StrategyVersion)
                .where(StrategyVersion.strategy_id == strategy.id)
                .order_by(StrategyVersion.is_current.desc(), StrategyVersion.id.desc())
            )
        ).all()
        self.operating_successfully(_build_detail(strategy, list(versions)))


class CreateStrategyViewModel(_AuthedStrategyViewModel):
    """新建用户私有策略（含初始 v1.0 版本记录）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: StrategyCreateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.form = form

    async def before(self) -> None:
        self.checker.require_auth()
        name = self.form.name.strip()
        if not name:
            self.illegal_parameters("策略名称不能为空")
            return

        params: list[list[str]] = self.form.params or _DEFAULT_PARAMS.get(self.form.strategyType, [])
        strategy = Strategy(
            user_id=int(self.checker.user_id),
            name=name,
            strategy_type=self.form.strategyType,
            timeframe=self.form.timeframe,
            market=(self.form.market or "").strip(),
            status=StrategyStatusEnum.TESTING,
            is_builtin=False,
            params=params,
            tags=[_TYPE_LABELS.get(self.form.strategyType, ""), self.form.timeframe],
            source_code=_build_source_stub(name, self.form.timeframe, params),
        )
        self.db.add(strategy)
        await self.db.flush()

        self.db.add(
            StrategyVersion(
                strategy_id=strategy.id,
                version="v1.0",
                is_current=True,
                changelog="初版创建",
                params_snapshot=params,
            )
        )
        await self.db.commit()
        await self.db.refresh(strategy)
        self.operating_successfully(_build_detail(strategy, []))


class ImportStrategyViewModel(_AuthedStrategyViewModel):
    """导入 Freqtrade 策略（保存源码 + 初始版本）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: StrategyImportForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.form = form

    async def before(self) -> None:
        self.checker.require_auth()
        name = self.form.name.strip()
        if not name:
            self.illegal_parameters("策略名称不能为空")
            return
        if not self.form.sourceCode.strip():
            self.illegal_parameters("策略源码不能为空")
            return

        params = _DEFAULT_PARAMS.get(self.form.strategyType, [])
        strategy = Strategy(
            user_id=int(self.checker.user_id),
            name=name,
            strategy_type=self.form.strategyType,
            timeframe=self.form.timeframe,
            status=StrategyStatusEnum.TESTING,
            is_builtin=False,
            params=params,
            tags=[_TYPE_LABELS.get(self.form.strategyType, ""), "导入"],
            source_code=self.form.sourceCode.strip(),
            description="由 Freqtrade 策略文件导入",
        )
        self.db.add(strategy)
        await self.db.flush()
        self.db.add(
            StrategyVersion(
                strategy_id=strategy.id,
                version="v1.0",
                is_current=True,
                changelog="导入初始版本",
                params_snapshot=params,
            )
        )
        await self.db.commit()
        await self.db.refresh(strategy)
        self.operating_successfully(_build_detail(strategy, []))


class UpdateStrategyViewModel(_AuthedStrategyViewModel):
    """更新策略参数（仅本人私有策略，内置策略只读）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: StrategyUpdateForm,
        checker: PermissionChecker,
        strategy_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.form = form
        self.strategy_id = strategy_id

    async def before(self) -> None:
        self.checker.require_auth()
        strategy = await self._load_visible_strategy(self.strategy_id)
        if strategy is None:
            self.not_found("策略不存在")
            return
        if strategy.is_builtin or strategy.user_id is None:
            self.forbidden("内置策略不可修改")
            return

        changes: dict[str, Any] = {}
        if self.form.name is not None:
            name = self.form.name.strip()
            if not name:
                self.illegal_parameters("策略名称不能为空")
                return
            strategy.name = name
            changes["name"] = name
        if self.form.timeframe is not None:
            strategy.timeframe = self.form.timeframe
            changes["timeframe"] = self.form.timeframe
        if self.form.market is not None:
            strategy.market = self.form.market.strip()
        if self.form.params is not None:
            strategy.params = self.form.params
            strategy.source_code = _build_source_stub(strategy.name, strategy.timeframe, self.form.params)
            changes["params"] = self.form.params

        if not changes and self.form.market is None:
            self.nothing_changed()
            return

        await self.db.commit()
        await self.db.refresh(strategy)
        versions = (
            await self.db.scalars(
                select(StrategyVersion)
                .where(StrategyVersion.strategy_id == strategy.id)
                .order_by(StrategyVersion.is_current.desc(), StrategyVersion.id.desc())
            )
        ).all()
        self.operating_successfully(_build_detail(strategy, list(versions)))


class SubmitStrategyBacktestViewModel(_AuthedStrategyViewModel):
    """提交回测（入口占位：真实回测在 backtests 域）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        strategy_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.strategy_id = strategy_id

    async def before(self) -> None:
        self.checker.require_auth()
        strategy = await self._load_visible_strategy(self.strategy_id)
        if strategy is None:
            self.not_found("策略不存在")
            return

        # 占位：真实任务创建与执行在 backtests 域；此处仅回执已受理。
        self.operating_successfully(
            StrategyBacktestSubmitResponseData(
                taskId=f"bt_pending_{strategy.id}",
                strategyId=strategy.id,
                status="queued",
                message=f"{strategy.name} 回测任务已提交 · 运行中",
            )
        )
