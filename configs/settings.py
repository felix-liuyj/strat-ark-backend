"""Application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = (
    "Settings",
    "get_settings",
)


class Settings(BaseSettings):
    APP_NAME: str = "Strat Ark Backend API"
    APP_NO: str = "strat-ark-backend"
    APP_ENV: str = "local"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/strat_ark"
    DATABASE_SCHEMA: str | None = "public"

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_USERNAME: str | None = "default"
    REDIS_PASSWORD: str | None = None
    REDIS_SSL: bool = False

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7
    JWT_REFRESH_EXPIRE_DAYS: int = 30
    ADMIN_EMAIL_SUFFIXES: str = ""

    OAUTH_GOOGLE_CLIENT_ID: str | None = None
    OAUTH_MICROSOFT_CLIENT_ID: str | None = None
    OAUTH_MICROSOFT_TENANT: str = "common"
    OAUTH_TOKEN_TIMEOUT_SECONDS: float = 10.0
    # client_secret 仅在 IdP 注册为 Web（机密）客户端时需要：Google Web 应用即使走 PKCE
    # 也要求 token 端点带 client_secret；注册为纯 public/SPA 客户端时留空即可（仅 PKCE）。
    # 永远只在后端持有，绝不下发前端。
    OAUTH_GOOGLE_CLIENT_SECRET: str | None = None
    OAUTH_MICROSOFT_CLIENT_SECRET: str | None = None

    # 业务敏感数据加密配置
    ENCRYPT_KEY: str | None = None

    ALI_OSS_ACCESS_KEY: str | None = None
    ALI_OSS_ACCESS_SECRET: str | None = None
    ALI_OSS_REGION: str | None = None
    ALI_OSS_BUCKET_NAME: str | None = None
    # 邮件 logo 在 OSS 中的 object key（path），host 由 ALI_OSS_BUCKET_NAME +
    # ALI_OSS_REGION 拼出（见 brand_logo_url）。留空或 OSS 配置缺失时，
    # 验证码邮件模板自动留空 logo 区域，不影响发信。
    BRAND_LOGO_OSS_PATH: str = ""

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 465
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_SENDER: str | None = None
    SMTP_USE_SSL: bool = True

    # 行情数据源
    # REST base 默认 Binance 公共行情（无需密钥）；可覆盖为自建代理 / 镜像以规避区域封锁。
    MARKET_DATA_REST_URL: str = "https://api.binance.com"
    MARKET_DATA_WS_URL: str | None = None
    MARKET_DATA_API_KEY: str | None = None

    # AI 投研 LLM 网关（TradingAgents 多智能体研报；provider-neutral）
    # 留空即回退确定性拟真研报、不发起任何 LLM 请求；AI 仅产出辅助决策，绝不直接下单。
    # provider: anthropic（Messages API）| openai（OpenAI 兼容 chat/completions 网关）。
    AI_GATEWAY_PROVIDER: str = "anthropic"
    AI_GATEWAY_URL: str | None = None
    AI_GATEWAY_API_KEY: str | None = None
    AI_GATEWAY_MODEL: str = "claude-opus-4-8"

    # 交易所私有 REST（账户信息查询：余额 / 权限，非下单）
    # 默认 Binance 现货 REST；GET /api/v3/account 需 HMAC-SHA256 签名 + X-MBX-APIKEY 头。
    # 仅当 view_model 能拿到可用的明文 api_key + api_secret 时才发起真实请求，
    # 否则（掩码 key / 空 secret / 占位密文）一律回退确定性拟真数据。
    EXCHANGE_API_BASE: str = "https://api.binance.com"

    # 引擎运行时（freqtrade / tradingagents）经服务连接交互：地址存于各引擎的
    # connection_config.serviceUrl（引擎配置页 UI 管理），不走 env，无需 K8s 集群化配置。

    # Stripe 支付（订阅 Checkout + Customer Portal + Webhook；官方 stripe SDK）
    # 留空 STRIPE_SECRET_KEY 即回退现有 mock 计费流程，应用仍可运行。
    # 价格 ID 来自 Stripe 控制台（每个套餐 × 计费周期一个 Price）；免费套餐无 Price。
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_PRO_MONTHLY: str | None = None
    STRIPE_PRICE_PRO_YEARLY: str | None = None
    STRIPE_PRICE_TEAM_MONTHLY: str | None = None
    STRIPE_PRICE_TEAM_YEARLY: str | None = None
    # Checkout success/cancel 与 Portal 返回地址基址；留空则取首个 CORS origin。
    FRONTEND_BASE_URL: str | None = None

    STATIC_DIR: str = "./statics"
    STATIC_URL: str = "/statics"

    model_config = SettingsConfigDict(
        env_file=f"{Path(__file__).resolve().parent.parent}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @computed_field
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @computed_field
    @property
    def stripe_enabled(self) -> bool:
        """是否已配置 Stripe（未配置则订阅走 mock 回退）。"""
        return bool(self.STRIPE_SECRET_KEY)

    @computed_field
    @property
    def frontend_base_url(self) -> str:
        """前端基址（Checkout / Portal 返回地址用），默认取首个 CORS origin。"""
        if self.FRONTEND_BASE_URL:
            return self.FRONTEND_BASE_URL.rstrip("/")
        origins = self.cors_origin_list
        return origins[0].rstrip("/") if origins else "http://localhost:3000"

    @computed_field
    @property
    def brand_logo_url(self) -> str | None:
        """系统 logo 的公开访问 URL：``https://{bucket}.oss-{region}.aliyuncs.com/{path}``。

        host 部分从 ``ALI_OSS_BUCKET_NAME`` + ``ALI_OSS_REGION`` 拼接，``path`` 取自
        ``BRAND_LOGO_OSS_PATH``。任一 OSS 字段缺失时返回 None，让模板层回落到 inline
        SVG / 文字 logo——开发本地 / 单元测试可不配 OSS 仍能正常发邮件。
        """
        bucket = (self.ALI_OSS_BUCKET_NAME or "").strip()
        region = (self.ALI_OSS_REGION or "").strip()
        path = (self.BRAND_LOGO_OSS_PATH or "").strip().lstrip("/")
        if not bucket or not region or not path:
            return None
        # 与 libs/ctrl/cloud/oss.py:access_url_prefix 同一拼接口径，避免两处分歧。
        return f"https://{bucket}.oss-{region}.aliyuncs.com/{path}"

    @computed_field
    @property
    def admin_email_suffix_list(self) -> list[str]:
        suffixes: list[str] = []
        for suffix in self.ADMIN_EMAIL_SUFFIXES.split(","):
            normalized = suffix.strip().lower()
            if not normalized:
                continue
            if normalized.startswith("@"):
                normalized = normalized[1:]
            suffixes.append(normalized)
        return suffixes

    def is_admin_email(self, email: str) -> bool:
        normalized_email = email.strip().lower()
        if "@" not in normalized_email:
            return False

        email_domain = normalized_email.rsplit("@", 1)[1]
        for suffix in self.admin_email_suffix_list:
            if email_domain == suffix or email_domain.endswith(f".{suffix}"):
                return True
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
