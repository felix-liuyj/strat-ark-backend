"""API router registry：聚合各业务域路由。"""

from fastapi import APIRouter

from api.ai import router as ai_router
from api.audit import router as audit_router
from api.auth import router as auth_router
from api.backtests import router as backtests_router
from api.bots import router as bots_router
from api.common import common_router
from api.dashboard import router as dashboard_router
from api.engine import router as engine_router
from api.exchanges import router as exchanges_router
from api.market import router as market_router
from api.notification import router as notification_router
from api.risk import router as risk_router
from api.settings import router as settings_router
from api.signals import router as signals_router
from api.strategies import router as strategies_router
from api.subscription import router as subscription_router
from api.trades import router as trades_router
from api.user_center import router as user_center_router

__all__ = ("api_router",)

api_router = APIRouter()
api_router.include_router(common_router)
api_router.include_router(auth_router)
api_router.include_router(dashboard_router)
api_router.include_router(exchanges_router)
api_router.include_router(bots_router)
api_router.include_router(strategies_router)
api_router.include_router(backtests_router)
api_router.include_router(signals_router)
api_router.include_router(ai_router)
api_router.include_router(risk_router)
api_router.include_router(trades_router)
api_router.include_router(market_router)
api_router.include_router(notification_router)
api_router.include_router(engine_router)
api_router.include_router(audit_router)
api_router.include_router(subscription_router)
api_router.include_router(settings_router)
api_router.include_router(user_center_router)
