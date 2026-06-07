"""风控引擎 service stub。

真实实现会对接平台风控服务：每次下单 / 切实盘前调用风控评估，触发硬性限额则
自动拦截订单或停止策略，并落地风控事件。当前阶段返回**拟真 mock**：与前端
RiskCenterPage 的总览、分层、规则、触发记录数据形状对齐。ViewModel 只调用这里的函数。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = (
    "RiskAssessmentResult",
    "RiskMetric",
    "RiskOverview",
    "assess_order",
    "get_risk_overview",
)


@dataclass(slots=True)
class RiskMetric:
    """单项风控指标（当前值 / 限额值，用于总览三栏）。"""

    key: str
    label: str
    current: float
    limit: float
    unit: str


@dataclass(slots=True)
class RiskOverview:
    """风险总览（总体状态 + 待处理告警数 + 关键指标）。"""

    overall_status: str
    pending_alerts: int
    metrics: list[RiskMetric] = field(default_factory=list)


@dataclass(slots=True)
class RiskAssessmentResult:
    """风控评估结果（下单 / 切实盘前）。"""

    approved: bool
    breached_rules: list[str]
    message: str


def get_risk_overview() -> RiskOverview:
    """返回风险总览（拟真静态值，与前端总览卡对齐）。

    真实实现：聚合账户权益、回撤、总敞口等实时指标与未处理告警计数。
    """
    return RiskOverview(
        overall_status="normal",
        pending_alerts=0,
        metrics=[
            RiskMetric(key="daily_loss", label="今日亏损", current=1.2, limit=3.0, unit="%"),
            RiskMetric(key="drawdown", label="账户回撤", current=6.2, limit=10.0, unit="%"),
            RiskMetric(key="exposure", label="总敞口", current=17.0, limit=60.0, unit="%"),
        ],
    )


def assess_order(symbol: str, side: str, quantity: float, leverage: float) -> RiskAssessmentResult:
    """下单前风控评估（mock）。

    真实实现：把订单参数送入风控引擎，校验各层硬性限额，命中即拒绝并返回触发规则。
    当前 stub 一律放行，仅作为业务层调用契约占位。
    """
    return RiskAssessmentResult(
        approved=True,
        breached_rules=[],
        message=f"{symbol} {side} 入场已批准",
    )
