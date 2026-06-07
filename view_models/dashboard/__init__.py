"""Dashboard 聚合 ViewModel。"""

from typing import Any

from fastapi import Request

from libs.auth.permissions import PermissionChecker
from responses.dashboard import (
    DashboardAiSummaryResponseData,
    DashboardBotResponseData,
    DashboardMetricResponseData,
    DashboardOverviewResponseData,
    DashboardPositionResponseData,
    DashboardRiskLimitResponseData,
    DashboardRiskStatusResponseData,
    DashboardSignalResponseData,
    DashboardTopbarResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = ("GetDashboardOverviewViewModel",)

_RISK_LIMITS: tuple[dict[str, Any], ...] = (
    {
        "key": "dailyLoss",
        "labelKey": "dashboard.dailyLossLimit",
        "currentLabel": "1.2%",
        "limitLabel": "3%",
        "safe": True,
    },
    {
        "key": "maxDrawdown",
        "labelKey": "dashboard.maxDrawdownLimit",
        "currentLabel": "6.2%",
        "limitLabel": "10%",
        "safe": True,
    },
    {
        "key": "singleExposure",
        "labelKey": "dashboard.singleExposure",
        "currentLabel": "4.1%",
        "limitLabel": "5%",
        "safe": True,
    },
    {"key": "losingStreak", "labelKey": "dashboard.losingStreak", "currentLabel": "1", "limitLabel": "3", "safe": True},
)

_METRICS: tuple[dict[str, Any], ...] = (
    {
        "key": "totalEquity",
        "labelKey": "dashboard.totalEquity",
        "value": 248512.0,
        "valueLabel": "$248,512",
        "changeLabel": "+$6,860 dashboard.today",
        "tone": "brand",
        "sparkline": [24, 22, 25, 18, 20, 12, 15, 7, 5],
    },
    {
        "key": "todayPnl",
        "labelKey": "dashboard.todayPnl",
        "value": 2.84,
        "valueLabel": "+2.84%",
        "changeLabel": "+$6,860",
        "tone": "positive",
        "sparkline": [21, 18, 19, 16, 12, 13, 10, 8, 6],
    },
    {
        "key": "activeBots",
        "labelKey": "dashboard.activeBots",
        "value": 2.0,
        "valueLabel": "2 / 3",
        "changeLabel": "status.running",
        "tone": "brand",
        "sparkline": [12, 12, 10, 10, 8, 8, 6, 6, 6],
    },
    {
        "key": "winRate",
        "labelKey": "dashboard.winRate",
        "value": 64.0,
        "valueLabel": "64%",
        "changeLabel": "30D",
        "tone": "positive",
        "sparkline": [25, 20, 23, 19, 18, 14, 15, 12, 10],
    },
)

_BOTS: tuple[dict[str, Any], ...] = (
    {
        "id": "btc-trend",
        "icon": "trend",
        "name": "BTC Trend Bot",
        "subtitle": "TrendV1 · Binance · 15m",
        "status": "running",
        "pnlLabel": "+2.3%",
        "positionsLabelKey": "dashboard.positions2",
    },
    {
        "id": "eth-mean",
        "icon": "mean",
        "name": "ETH Mean Rev",
        "subtitle": "RSI-BB · Binance · 5m",
        "status": "dry",
        "pnlLabel": "+0.8%",
        "positionsLabelKey": "dashboard.positions1",
    },
    {
        "id": "sol-breakout",
        "icon": "breakout",
        "name": "SOL Breakout",
        "subtitle": "Donchian · Bybit · 1h",
        "status": "stopped",
        "pnlLabel": "-",
        "positionsLabelKey": "dashboard.positions0",
    },
)

_SIGNALS: tuple[dict[str, Any], ...] = (
    {
        "id": "sig-btc-1030",
        "time": "10:30",
        "symbol": "BTC/USDT",
        "direction": "long",
        "source": "AI + Strategy",
        "confidenceLabel": "72%",
        "riskLevelKey": "strategy.riskMed",
        "status": "pending",
    },
    {
        "id": "sig-eth-1012",
        "time": "10:12",
        "symbol": "ETH/USDT",
        "direction": "long",
        "source": "Strategy",
        "confidenceLabel": "64%",
        "riskLevelKey": "strategy.riskLow",
        "status": "approved",
    },
    {
        "id": "sig-sol-0948",
        "time": "09:48",
        "symbol": "SOL/USDT",
        "direction": "short",
        "source": "AI",
        "confidenceLabel": "58%",
        "riskLevelKey": "strategy.riskHigh",
        "status": "rejected",
    },
    {
        "id": "sig-bnb-0930",
        "time": "09:30",
        "symbol": "BNB/USDT",
        "direction": "neutral",
        "source": "Webhook",
        "confidenceLabel": "51%",
        "riskLevelKey": "strategy.riskMed",
        "status": "expired",
    },
)

_POSITIONS: tuple[dict[str, Any], ...] = (
    {
        "symbol": "BTC/USDT",
        "direction": "long",
        "entryPriceLabel": "67,420",
        "markPriceLabel": "68,610",
        "sizeLabel": "0.32",
        "valueLabel": "$21,955",
        "pnlLabel": "+$380 (+1.8%)",
        "botName": "BTC Trend Bot",
    },
    {
        "symbol": "ETH/USDT",
        "direction": "long",
        "entryPriceLabel": "3,448",
        "markPriceLabel": "3,512",
        "sizeLabel": "3.1",
        "valueLabel": "$10,887",
        "pnlLabel": "+$198 (+1.9%)",
        "botName": "ETH Mean Rev",
    },
    {
        "symbol": "BTC/USDT",
        "direction": "long",
        "entryPriceLabel": "68,050",
        "markPriceLabel": "68,610",
        "sizeLabel": "0.13",
        "valueLabel": "$8,919",
        "pnlLabel": "+$73 (+0.8%)",
        "botName": "BTC Trend Bot",
    },
)


class GetDashboardOverviewViewModel(BaseViewModel):
    """Dashboard 页面聚合入口。"""

    def __init__(self, request: Request, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        self.operating_successfully(_build_overview())


def _build_overview() -> DashboardOverviewResponseData:
    return DashboardOverviewResponseData(
        topbar=_build_topbar(),
        risk=_build_risk(),
        metrics=[DashboardMetricResponseData(**item) for item in _METRICS],
        aiSummary=_build_ai_summary(),
        bots=[DashboardBotResponseData(**item) for item in _BOTS],
        signals=[DashboardSignalResponseData(**item) for item in _SIGNALS],
        positions=[DashboardPositionResponseData(**item) for item in _POSITIONS],
    )


def _build_topbar() -> DashboardTopbarResponseData:
    return DashboardTopbarResponseData(
        totalEquity=248512.0,
        totalEquityLabel="$248,512",
        todayPnlPct=2.84,
        todayPnlLabel="+2.84%",
        mode="dry",
        unreadNotifications=1,
    )


def _build_risk() -> DashboardRiskStatusResponseData:
    return DashboardRiskStatusResponseData(
        status="healthy",
        headlineKey="dashboard.systemNormal",
        statusKey="dashboard.systemHealthy",
        limits=[DashboardRiskLimitResponseData(**item) for item in _RISK_LIMITS],
    )


def _build_ai_summary() -> DashboardAiSummaryResponseData:
    return DashboardAiSummaryResponseData(
        bias="moderately_bullish",
        confidencePct=68,
        updatedLabel="5m ago",
        summary="BTC 与 ETH 维持多头结构，波动率温和回升；SOL 短线突破失败后需要等待新的量能确认。",
        focusSymbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
    )
