"""部署期种入且运行时只读的系统目录默认值。"""

from typing import Any

from models.account import PlanEnum
from models.engine import EngineKindEnum

__all__ = ("ENGINE_CATALOG", "PLAN_CATALOG")

ENGINE_CATALOG: dict[EngineKindEnum, dict[str, Any]] = {
    EngineKindEnum.FREQTRADE: {
        "name": "Freqtrade 执行引擎",
        "connection_config": {
            "orchestratorUrl": "http://freqtrade-orchestrator:8090",
            "orchestratorToken": "",
            "instanceImage": "",
            "timeout": 30,
        },
        "deployment_config": {"logLevel": "INFO", "scheduler": 8},
    },
    EngineKindEnum.TRADINGAGENTS: {
        "name": "TradingAgents API 服务",
        "connection_config": {
            "serviceUrl": "http://tradingagents-api:8100",
            "timeout": 60,
            "gatewayProvider": "Anthropic",
            "gatewayEndpoint": "https://api.anthropic.com",
            "gatewayModel": "claude-sonnet",
            "apiKey": "",
        },
        "deployment_config": {
            "logLevel": "INFO",
            "concurrency": 8,
            "temperature": 0.3,
            "maxTokens": 4096,
        },
    },
}

PLAN_CATALOG: list[dict[str, Any]] = [
    {
        "code": PlanEnum.FREE,
        "name": "subscription.plan.free",
        "tagline": "subscription.tagline.free",
        "price_monthly": 0,
        "price_yearly_per_month": 0,
        "highlight": False,
        "features": [
            "subscription.feat.free.bots",
            "subscription.feat.free.strategies",
            "subscription.feat.free.ai",
            "subscription.feat.free.dryrun",
        ],
        "limit_bots": 1,
        "limit_strategies": 3,
        "limit_ai_analysis": 20,
        "limit_backtests": 10,
        "sort_order": 0,
    },
    {
        "code": PlanEnum.PRO,
        "name": "subscription.plan.pro",
        "tagline": "subscription.tagline.pro",
        "price_monthly": 49,
        "price_yearly_per_month": 41,
        "highlight": True,
        "features": [
            "subscription.feat.pro.bots",
            "subscription.feat.pro.strategies",
            "subscription.feat.pro.ai",
            "subscription.feat.pro.live",
        ],
        "limit_bots": 10,
        "limit_strategies": 20,
        "limit_ai_analysis": 300,
        "limit_backtests": -1,
        "sort_order": 1,
    },
    {
        "code": PlanEnum.TEAM,
        "name": "subscription.plan.team",
        "tagline": "subscription.tagline.team",
        "price_monthly": 149,
        "price_yearly_per_month": 124,
        "highlight": False,
        "features": [
            "subscription.feat.team.bots",
            "subscription.feat.team.strategies",
            "subscription.feat.team.ai",
            "subscription.feat.team.live",
        ],
        "limit_bots": -1,
        "limit_strategies": -1,
        "limit_ai_analysis": 2000,
        "limit_backtests": -1,
        "sort_order": 2,
    },
]
