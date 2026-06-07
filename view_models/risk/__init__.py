"""风控中心视图模型。

风险总览 / 分层卡来自风控引擎 service（拟真）；风控规则与触发记录读写数据库。
规则列表为空时回落到 service 提供的默认规则集（只读，不隐式落库，避免 GET 写库）。
"""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.risk import (
    RiskEventCreateForm,
    RiskRuleCreateForm,
    RiskRulesBulkUpdateForm,
    RiskRuleUpdateForm,
)
from libs.auth.permissions import PermissionChecker
from libs.integrations import risk_engine
from models.risk import RiskEvent, RiskEventLevelEnum, RiskRule, RiskRuleScopeEnum, RiskRuleTypeEnum
from responses.risk import (
    RiskEventResponseData,
    RiskLevelCardResponseData,
    RiskMetricResponseData,
    RiskOverviewResponseData,
    RiskRuleResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = (
    "CreateRiskEventViewModel",
    "CreateRiskRuleViewModel",
    "ListRiskEventsViewModel",
    "ListRiskLevelsViewModel",
    "ListRiskRulesViewModel",
    "RiskOverviewViewModel",
    "UpdateRiskRuleViewModel",
    "UpdateRiskRulesBulkViewModel",
)


# 默认风控规则集（规则列表为空时只读回落，与前端 RULES 八条对齐）。
# 元组列：(scope, rule_type, label, current_value, limit_value, unit)。
_DefaultRule = tuple[RiskRuleScopeEnum, RiskRuleTypeEnum, str, float | None, float | None, str]
_DEFAULT_RULES: list[_DefaultRule] = [
    (RiskRuleScopeEnum.ACCOUNT, RiskRuleTypeEnum.DAILY_LOSS_LIMIT, "risk.ruleDailyLoss", 1.2, 3.0, "%"),
    (RiskRuleScopeEnum.ACCOUNT, RiskRuleTypeEnum.MAX_DRAWDOWN, "risk.ruleMaxDrawdown", 6.2, 10.0, "%"),
    (RiskRuleScopeEnum.SYMBOL, RiskRuleTypeEnum.MAX_POSITION_SIZE, "risk.ruleMaxPosition", 4.1, 5.0, "%"),
    (RiskRuleScopeEnum.ORDER, RiskRuleTypeEnum.MAX_LEVERAGE, "risk.ruleMaxLeverage", 1.0, 3.0, "x"),
    (RiskRuleScopeEnum.STRATEGY, RiskRuleTypeEnum.COOLDOWN, "risk.ruleCooldown", 1.0, 3.0, "次"),
    (RiskRuleScopeEnum.SIGNAL, RiskRuleTypeEnum.NEWS_FILTER, "risk.ruleNews", None, None, ""),
    (RiskRuleScopeEnum.SIGNAL, RiskRuleTypeEnum.VOLATILITY_FILTER, "risk.ruleVolatility", None, None, ""),
    (RiskRuleScopeEnum.SYMBOL, RiskRuleTypeEnum.LIQUIDITY_FILTER, "risk.ruleLiquidity", None, None, ""),
]

# 默认分层卡（与前端 6 张分层卡对齐）。
# 元组列：(scope, title, subtitle, status, status_label)。
_DefaultLevel = tuple[RiskRuleScopeEnum, str, str, str, str]
_DEFAULT_LEVELS: list[_DefaultLevel] = [
    (RiskRuleScopeEnum.ACCOUNT, "risk.levelAccount", "risk.levelAccountSub", "run", "status.normal"),
    (RiskRuleScopeEnum.BOT, "risk.levelBot", "risk.levelBotSub", "run", "status.normal"),
    (RiskRuleScopeEnum.STRATEGY, "risk.levelStrategy", "risk.levelStrategySub", "warn", "status.watch"),
    (RiskRuleScopeEnum.SYMBOL, "risk.levelPosition", "risk.levelPositionSub", "warn", "status.watch"),
    (RiskRuleScopeEnum.ORDER, "risk.levelOrder", "risk.levelOrderSub", "run", "status.normal"),
    (RiskRuleScopeEnum.SIGNAL, "risk.levelSignal", "risk.levelSignalSub", "run", "status.normal"),
]

# 默认触发记录（事件表为空时只读回落，与前端 EVENTS 五条对齐）。
# 元组列：(level, scope, rule_type, title, description, symbol, occurred_at)。
_DefaultEvent = tuple[RiskEventLevelEnum, RiskRuleScopeEnum, RiskRuleTypeEnum | None, str, str, str | None, str]
_DEFAULT_EVENTS: list[_DefaultEvent] = [
    (
        RiskEventLevelEnum.WARN,
        RiskRuleScopeEnum.SYMBOL,
        RiskRuleTypeEnum.VOLATILITY_FILTER,
        "risk.evVolatility",
        "risk.evVolatilityDesc",
        "SOL/USDT",
        "08:15",
    ),
    (
        RiskEventLevelEnum.DANGER,
        RiskRuleScopeEnum.SIGNAL,
        None,
        "risk.evRejected",
        "risk.evRejectedDesc",
        "DOGE/USDT",
        "08:50",
    ),
    (
        RiskEventLevelEnum.WARN,
        RiskRuleScopeEnum.SYMBOL,
        RiskRuleTypeEnum.MAX_POSITION_SIZE,
        "risk.evExposure",
        "risk.evExposureDesc",
        "BTC/USDT",
        "09:30",
    ),
    (
        RiskEventLevelEnum.SUCCESS,
        RiskRuleScopeEnum.ORDER,
        None,
        "risk.evApproved",
        "risk.evApprovedDesc",
        "BTC/USDT",
        "10:28",
    ),
    (RiskEventLevelEnum.INFO, RiskRuleScopeEnum.ACCOUNT, None, "risk.evScan", "risk.evScanDesc", None, "10:00"),
]


def _rule_to_response(rule: RiskRule) -> RiskRuleResponseData:
    return RiskRuleResponseData(
        id=rule.id,
        scope=rule.scope,
        ruleType=rule.rule_type,
        label=rule.label,
        currentValue=rule.current_value,
        limitValue=rule.limit_value,
        unit=rule.unit,
        enabled=rule.enabled,
        botId=rule.bot_id,
        strategyId=rule.strategy_id,
        symbol=rule.symbol,
        description=rule.description,
    )


def _default_rule_to_response(index: int, item: _DefaultRule) -> RiskRuleResponseData:
    # 默认规则用负数 id 标记「未落库」，前端编辑后由 bulk update 写入正式记录。
    scope, rule_type, label, current_value, limit_value, unit = item
    return RiskRuleResponseData(
        id=-(index + 1),
        scope=scope,
        ruleType=rule_type,
        label=label,
        currentValue=current_value,
        limitValue=limit_value,
        unit=unit,
        enabled=True,
        botId=None,
        strategyId=None,
        symbol=None,
        description="",
    )


def _event_to_response(event: RiskEvent) -> RiskEventResponseData:
    return RiskEventResponseData(
        id=event.id,
        level=event.level,
        scope=event.scope,
        ruleType=event.rule_type,
        title=event.title,
        description=event.description,
        symbol=event.symbol,
        actionTaken=event.action_taken,
        resolved=event.resolved,
        occurredAt=event.occurred_at,
    )


def _default_event_to_response(index: int, item: _DefaultEvent) -> RiskEventResponseData:
    level, scope, rule_type, title, description, symbol, occurred_at = item
    return RiskEventResponseData(
        id=-(index + 1),
        level=level,
        scope=scope,
        ruleType=rule_type,
        title=title,
        description=description,
        symbol=symbol,
        actionTaken=None,
        resolved=False,
        occurredAt=occurred_at,
    )


class RiskOverviewViewModel(BaseViewModel):
    """风险总览（总体状态 + 待处理告警 + 关键指标）。"""

    def __init__(self, request: Request, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        overview = risk_engine.get_risk_overview()
        data = RiskOverviewResponseData(
            overallStatus=overview.overall_status,
            pendingAlerts=overview.pending_alerts,
            metrics=[
                RiskMetricResponseData(key=m.key, label=m.label, current=m.current, limit=m.limit, unit=m.unit)
                for m in overview.metrics
            ],
        )
        self.operating_successfully(data)


class ListRiskLevelsViewModel(BaseViewModel):
    """风控分层卡列表（账户 / Bot / 策略 / 持仓 / 订单 / AI 信号级）。"""

    def __init__(self, request: Request, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        cards = [
            RiskLevelCardResponseData(
                scope=scope,
                title=title,
                subtitle=subtitle,
                status=status,
                statusLabel=status_label,
            )
            for scope, title, subtitle, status, status_label in _DEFAULT_LEVELS
        ]
        self.operating_successfully(cards)


class ListRiskRulesViewModel(BaseViewModel):
    """风控规则列表（DB 为空时只读回落默认规则集）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        rules = (
            await self.db.scalars(
                select(RiskRule).where(RiskRule.user_id == int(self.checker.user_id)).order_by(RiskRule.id.asc())
            )
        ).all()
        if rules:
            self.operating_successfully([_rule_to_response(r) for r in rules])
            return
        defaults = [_default_rule_to_response(i, item) for i, item in enumerate(_DEFAULT_RULES)]
        self.operating_successfully(defaults)


class ListRiskEventsViewModel(BaseViewModel):
    """风控触发记录列表（DB 为空时只读回落默认事件集）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        events = (
            await self.db.scalars(
                select(RiskEvent).where(RiskEvent.user_id == int(self.checker.user_id)).order_by(RiskEvent.id.desc())
            )
        ).all()
        if events:
            self.operating_successfully([_event_to_response(e) for e in events])
            return
        defaults = [_default_event_to_response(i, item) for i, item in enumerate(_DEFAULT_EVENTS)]
        self.operating_successfully(defaults)


class CreateRiskRuleViewModel(BaseViewModel):
    """创建单条风控规则。"""

    def __init__(
        self, request: Request, db: AsyncSession, form: RiskRuleCreateForm, checker: PermissionChecker
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        rule = RiskRule(
            user_id=int(self.checker.user_id),
            scope=self.form.scope,
            rule_type=self.form.ruleType,
            label=self.form.label.strip(),
            current_value=self.form.currentValue,
            limit_value=self.form.limitValue,
            unit=self.form.unit,
            enabled=self.form.enabled,
            bot_id=self.form.botId,
            strategy_id=self.form.strategyId,
            symbol=self.form.symbol,
            description=self.form.description,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        self.operating_successfully(_rule_to_response(rule))


class UpdateRiskRuleViewModel(BaseViewModel):
    """更新单条风控规则。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        rule_id: int,
        form: RiskRuleUpdateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.rule_id = rule_id
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        rule = await self.db.get(RiskRule, self.rule_id)
        if rule is None or rule.user_id != int(self.checker.user_id):
            self.not_found("风控规则不存在")
            return

        if self.form.label is not None:
            rule.label = self.form.label.strip()
        if self.form.currentValue is not None:
            rule.current_value = self.form.currentValue
        if self.form.limitValue is not None:
            rule.limit_value = self.form.limitValue
        if self.form.unit is not None:
            rule.unit = self.form.unit
        if self.form.enabled is not None:
            rule.enabled = self.form.enabled
        if self.form.description is not None:
            rule.description = self.form.description

        await self.db.commit()
        await self.db.refresh(rule)
        self.operating_successfully(_rule_to_response(rule))


class UpdateRiskRulesBulkViewModel(BaseViewModel):
    """批量下发风控规则（前端「编辑风控规则」弹窗：六阈值 + 三开关，落库全部规则）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: RiskRulesBulkUpdateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.form = form
        self.checker = checker

    def _build_rules(self, user_id: int) -> list[RiskRule]:
        form = self.form
        # 列：(scope, rule_type, label, limit_value, unit, enabled)。
        rows: list[tuple[RiskRuleScopeEnum, RiskRuleTypeEnum, str, float | None, str, bool]] = [
            (
                RiskRuleScopeEnum.ACCOUNT,
                RiskRuleTypeEnum.DAILY_LOSS_LIMIT,
                "Daily Loss Limit",
                form.dailyLossLimit,
                "%",
                True,
            ),
            (RiskRuleScopeEnum.ACCOUNT, RiskRuleTypeEnum.MAX_DRAWDOWN, "Max Drawdown", form.maxDrawdown, "%", True),
            (
                RiskRuleScopeEnum.SYMBOL,
                RiskRuleTypeEnum.MAX_POSITION_SIZE,
                "Max Position Size",
                form.maxPositionSize,
                "%",
                True,
            ),
            (RiskRuleScopeEnum.ORDER, RiskRuleTypeEnum.MAX_LEVERAGE, "Max Leverage", form.maxLeverage, "x", True),
            (
                RiskRuleScopeEnum.STRATEGY,
                RiskRuleTypeEnum.COOLDOWN,
                "Cooldown (连亏)",
                float(form.cooldownCount),
                "次",
                True,
            ),
            (RiskRuleScopeEnum.STRATEGY, RiskRuleTypeEnum.COOLDOWN, "冷却时长", form.cooldownHours, "h", True),
            (RiskRuleScopeEnum.SIGNAL, RiskRuleTypeEnum.NEWS_FILTER, "News Risk Filter", None, "", form.newsFilter),
            (
                RiskRuleScopeEnum.SYMBOL,
                RiskRuleTypeEnum.VOLATILITY_FILTER,
                "Volatility Filter",
                None,
                "",
                form.volatilityFilter,
            ),
            (
                RiskRuleScopeEnum.SYMBOL,
                RiskRuleTypeEnum.LIQUIDITY_FILTER,
                "Liquidity Filter",
                None,
                "",
                form.liquidityFilter,
            ),
        ]
        return [
            RiskRule(
                user_id=user_id,
                scope=scope,
                rule_type=rule_type,
                label=label,
                limit_value=limit_value,
                unit=unit,
                enabled=enabled,
            )
            for scope, rule_type, label, limit_value, unit, enabled in rows
        ]

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)
        # 全量覆盖：先删旧规则再写新规则，保证「一次下发」语义一致。
        existing = (await self.db.scalars(select(RiskRule).where(RiskRule.user_id == user_id))).all()
        for rule in existing:
            await self.db.delete(rule)
        new_rules = self._build_rules(user_id)
        self.db.add_all(new_rules)
        await self.db.commit()
        for rule in new_rules:
            await self.db.refresh(rule)
        self.operating_successfully([_rule_to_response(r) for r in new_rules])


class CreateRiskEventViewModel(BaseViewModel):
    """落地一条风控触发记录（评估命中 / 拦截后调用）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: RiskEventCreateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        event = RiskEvent(
            user_id=int(self.checker.user_id),
            level=self.form.level,
            scope=self.form.scope,
            rule_type=self.form.ruleType,
            title=self.form.title.strip(),
            description=self.form.description,
            symbol=self.form.symbol,
            action_taken=self.form.actionTaken,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        self.operating_successfully(_event_to_response(event))
