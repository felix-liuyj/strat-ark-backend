"""信号中心 ViewModel。

状态机：Generated → Reviewed → Approved → Executed；任意未终态可转 Rejected / Expired。
approve / reject / execute 为人工 + 风控动作；批准不等于自动下单。
"""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.signals import SignalCreateForm
from libs.auth.permissions import PermissionChecker
from models.signals import (
    Signal,
    SignalSourceEnum,
    SignalStatusEnum,
)
from responses.signals import SignalData
from view_models import BaseViewModel

__all__ = (
    "ApproveSignalViewModel",
    "CreateSignalViewModel",
    "ExecuteSignalViewModel",
    "ListSignalsViewModel",
    "RejectSignalViewModel",
)

# 状态机允许的迁移：源状态 → 可达目标状态集合。
_ALLOWED_TRANSITIONS: dict[SignalStatusEnum, set[SignalStatusEnum]] = {
    SignalStatusEnum.GENERATED: {
        SignalStatusEnum.REVIEWED,
        SignalStatusEnum.APPROVED,
        SignalStatusEnum.REJECTED,
        SignalStatusEnum.EXPIRED,
    },
    SignalStatusEnum.REVIEWED: {
        SignalStatusEnum.APPROVED,
        SignalStatusEnum.REJECTED,
        SignalStatusEnum.EXPIRED,
    },
    SignalStatusEnum.APPROVED: {
        SignalStatusEnum.EXECUTED,
        SignalStatusEnum.REJECTED,
        SignalStatusEnum.EXPIRED,
    },
    SignalStatusEnum.EXECUTED: set(),
    SignalStatusEnum.REJECTED: set(),
    SignalStatusEnum.EXPIRED: set(),
}


def _build_signal(signal: Signal) -> SignalData:
    return SignalData(
        id=signal.id,
        symbol=signal.symbol,
        direction=signal.direction,
        source=signal.source,
        confidence=signal.confidence,
        entryPrice=signal.entry_price,
        stopLoss=signal.stop_loss,
        takeProfit=signal.take_profit,
        riskLevel=signal.risk_level,
        status=signal.status,
        note=signal.note,
        createdAt=signal.created_at,
    )


def _can_transition(current: SignalStatusEnum, target: SignalStatusEnum) -> bool:
    return target in _ALLOWED_TRANSITIONS.get(current, set())


class ListSignalsViewModel(BaseViewModel):
    """信号列表，支持按状态与来源筛选（按生成时间倒序）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        status: str | None = None,
        source: str | None = None,
    ) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db
        self.status = status
        self.source = source

    async def before(self) -> None:
        self.checker.require_auth()

        statement = select(Signal).where(Signal.user_id == int(self.checker.user_id))
        if self.status:
            statement = statement.where(Signal.status == self.status)
        if self.source:
            statement = statement.where(Signal.source == self.source)
        statement = statement.order_by(Signal.created_at.desc())

        signals = (await self.db.scalars(statement)).all()
        self.operating_successfully([_build_signal(s) for s in signals])


class CreateSignalViewModel(BaseViewModel):
    """手动创建信号（来源固定 manual，初始状态 Generated）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: SignalCreateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        self.checker.require_auth()

        symbol = self.form.symbol.strip()
        if not symbol:
            self.illegal_parameters("交易对不能为空")
            return
        if not 0.0 <= self.form.confidence <= 1.0:
            self.illegal_parameters("置信度必须在 0 到 1 之间")
            return

        signal = Signal(
            user_id=int(self.checker.user_id),
            symbol=symbol,
            direction=self.form.direction,
            source=SignalSourceEnum.MANUAL,
            confidence=self.form.confidence,
            entry_price=self.form.entryPrice,
            stop_loss=self.form.stopLoss,
            take_profit=self.form.takeProfit,
            risk_level=self.form.riskLevel,
            status=SignalStatusEnum.GENERATED,
            note=self.form.note,
        )
        self.db.add(signal)
        await self.db.commit()
        await self.db.refresh(signal)

        self.operating_successfully(_build_signal(signal))


class _SignalTransitionViewModel(BaseViewModel):
    """信号状态迁移基类（approve / reject / execute 共用校验与落库）。"""

    target_status: SignalStatusEnum

    def __init__(self, request: Request, db: AsyncSession, signal_id: int, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.signal_id = signal_id
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        self.checker.require_auth()

        signal = await self.db.get(Signal, self.signal_id)
        if signal is None or signal.user_id != int(self.checker.user_id):
            self.not_found("信号不存在")
            return

        current = SignalStatusEnum(signal.status)
        if not _can_transition(current, self.target_status):
            self.illegal_parameters(f"信号当前状态 {current.value} 不可变更为 {self.target_status.value}")
            return

        signal.status = self.target_status
        await self.db.commit()
        await self.db.refresh(signal)
        self.operating_successfully(_build_signal(signal))


class ApproveSignalViewModel(_SignalTransitionViewModel):
    """批准信号（→ Approved）。批准不等于自动下单，仍受 Live Mode 与风控约束。"""

    target_status = SignalStatusEnum.APPROVED


class RejectSignalViewModel(_SignalTransitionViewModel):
    """拒绝信号（→ Rejected）。"""

    target_status = SignalStatusEnum.REJECTED


class ExecuteSignalViewModel(_SignalTransitionViewModel):
    """执行信号（→ Executed），仅允许从 Approved 迁移。"""

    target_status = SignalStatusEnum.EXECUTED
