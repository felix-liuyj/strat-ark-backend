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
    FRONTEND_DOMAIN: str = "http://localhost:3000"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/strat_ark"
    DATABASE_SCHEMA: str | None = "public"

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_USERNAME: str | None = "default"
    REDIS_PASSWORD: str | None = None

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7
    JWT_REFRESH_EXPIRE_DAYS: int = 30
    ADMIN_EMAIL_SUFFIXES: str = ""

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

    # ------------------------------------------------------------
    # 外部集成（当前以 libs/integrations/* stub 实现，以下为真实接入预留；
    # 留空时 stub 返回拟真 mock 数据，不影响本地运行与演示）。
    # ------------------------------------------------------------
    # 凭证加密密钥（交易所 / 网关 API Key 入库加密，stub 阶段仅掩码存储）
    ENCRYPT_KEY: str | None = None
    # Freqtrade 执行引擎编排
    FREQTRADE_ORCHESTRATOR_URL: str | None = None
    FREQTRADE_API_TOKEN: str | None = None
    # TradingAgents 投研引擎 / LLM 网关
    TRADINGAGENTS_API_URL: str | None = None
    LLM_GATEWAY_URL: str | None = None
    LLM_API_KEY: str | None = None
    LLM_DEFAULT_MODEL: str = "claude-sonnet"
    # 行情数据源
    MARKET_DATA_WS_URL: str | None = None
    MARKET_DATA_API_KEY: str | None = None
    # 集群 / 引擎运维（Kubernetes）
    K8S_NAMESPACE: str = "stratark-prod"
    K8S_IN_CLUSTER: bool = False
    # 通知渠道（敏感值建议由运行环境注入）
    TELEGRAM_BOT_TOKEN: str | None = None
    SLACK_WEBHOOK_URL: str | None = None
    LARK_WEBHOOK_URL: str | None = None

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
