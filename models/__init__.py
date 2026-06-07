"""ORM 模型注册表：import models 时触发全部表注册（init_db 依赖此聚合建表）。"""

from models.account import PlanEnum, UserTypeEnum
from models.ai import AgentReport, AgentReportTypeEnum
from models.audit_log import (
    ActorTypeEnum,
    AuditActionEnum,
    AuditCategoryEnum,
    AuditLog,
    AuditStatusEnum,
)
from models.backtests import BacktestStatusEnum, BacktestTask
from models.bot import Bot, BotRunModeEnum, BotStatusEnum, BotTradeModeEnum
from models.engine import (
    Engine,
    EngineKindEnum,
    EngineOp,
    EngineOpStatusEnum,
    EngineOpTypeEnum,
    EngineStatusEnum,
)
from models.exchange import (
    ExchangeAccount,
    ExchangePermissionEnum,
    ExchangeProviderEnum,
    ExchangeStatusEnum,
)
from models.market import MarketWatchlistItem
from models.notification import (
    ChannelKindEnum,
    Notification,
    NotificationChannel,
    NotificationSubscription,
    NotificationTypeEnum,
)
from models.risk import (
    RiskEvent,
    RiskEventLevelEnum,
    RiskRule,
    RiskRuleScopeEnum,
    RiskRuleTypeEnum,
)
from models.settings import SystemConfig, SystemConfigGroupEnum
from models.signals import (
    Signal,
    SignalDirectionEnum,
    SignalRiskLevelEnum,
    SignalSourceEnum,
    SignalStatusEnum,
)
from models.strategy import (
    Strategy,
    StrategyRiskEnum,
    StrategyStatusEnum,
    StrategyTypeEnum,
    StrategyVersion,
)
from models.subscription import (
    BillingCycleEnum,
    Invoice,
    InvoiceStatusEnum,
    Plan,
    Subscription,
    SubscriptionStatusEnum,
    UsageCounter,
    UsageMetricEnum,
)
from models.trade import (
    Order,
    OrderStatusEnum,
    OrderTypeEnum,
    Position,
    Trade,
    TradeSideEnum,
    TradeStatusEnum,
)
from models.user import User
from models.user_center import (
    ApiKeyPermissionEnum,
    OAuthBinding,
    OAuthProviderEnum,
    PlatformApiKey,
    UserSession,
)

__all__ = (
    "ActorTypeEnum",
    "AgentReport",
    "AgentReportTypeEnum",
    "ApiKeyPermissionEnum",
    "AuditActionEnum",
    "AuditCategoryEnum",
    "AuditLog",
    "AuditStatusEnum",
    "BacktestStatusEnum",
    "BacktestTask",
    "BillingCycleEnum",
    "Bot",
    "BotRunModeEnum",
    "BotStatusEnum",
    "BotTradeModeEnum",
    "ChannelKindEnum",
    "Engine",
    "EngineKindEnum",
    "EngineOp",
    "EngineOpStatusEnum",
    "EngineOpTypeEnum",
    "EngineStatusEnum",
    "ExchangeAccount",
    "ExchangePermissionEnum",
    "ExchangeProviderEnum",
    "ExchangeStatusEnum",
    "Invoice",
    "InvoiceStatusEnum",
    "MarketWatchlistItem",
    "Notification",
    "NotificationChannel",
    "NotificationSubscription",
    "NotificationTypeEnum",
    "OAuthBinding",
    "OAuthProviderEnum",
    "Order",
    "OrderStatusEnum",
    "OrderTypeEnum",
    "Plan",
    "PlanEnum",
    "PlatformApiKey",
    "Position",
    "RiskEvent",
    "RiskEventLevelEnum",
    "RiskRule",
    "RiskRuleScopeEnum",
    "RiskRuleTypeEnum",
    "Signal",
    "SignalDirectionEnum",
    "SignalRiskLevelEnum",
    "SignalSourceEnum",
    "SignalStatusEnum",
    "Strategy",
    "StrategyRiskEnum",
    "StrategyStatusEnum",
    "StrategyTypeEnum",
    "StrategyVersion",
    "Subscription",
    "SubscriptionStatusEnum",
    "SystemConfig",
    "SystemConfigGroupEnum",
    "Trade",
    "TradeSideEnum",
    "TradeStatusEnum",
    "UsageCounter",
    "UsageMetricEnum",
    "User",
    "UserSession",
    "UserTypeEnum",
)
