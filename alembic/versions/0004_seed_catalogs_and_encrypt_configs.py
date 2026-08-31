"""显式种入系统目录并加密历史敏感 JSON 配置。

读取接口不得承担 seed 或明文迁移。本迁移在部署期补齐套餐与引擎目录，并把历史
引擎 token、LLM API Key、通知 Bot Token 与 Webhook 地址转换为 Fernet 密文。

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-31
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from cryptography.fernet import Fernet

from alembic import op
from configs import get_settings
from libs.ctrl.db.sqlalchemy import Base

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = Base.metadata.schema
_CIPHER_PREFIX = "fernet::"
_ENGINE_SECRET_KEYS = frozenset(
    {"token", "apiKey", "secret", "restApiToken", "password", "orchestratorToken"}
)
_NOTIFICATION_SECRET_KEYS = frozenset(
    {"botToken", "secret", "apiKey", "token", "password", "url", "webhookUrl", "deviceToken"}
)


def _tables() -> tuple[sa.Table, sa.Table, sa.Table]:
    metadata = sa.MetaData()
    plans = sa.Table(
        "plans",
        metadata,
        sa.Column("id", sa.Integer),
        sa.Column("code", sa.String),
        sa.Column("name", sa.String),
        sa.Column("tagline", sa.String),
        sa.Column("price_monthly", sa.Numeric),
        sa.Column("price_yearly_per_month", sa.Numeric),
        sa.Column("highlight", sa.Boolean),
        sa.Column("features", sa.JSON),
        sa.Column("limit_bots", sa.Integer),
        sa.Column("limit_strategies", sa.Integer),
        sa.Column("limit_ai_analysis", sa.Integer),
        sa.Column("limit_backtests", sa.Integer),
        sa.Column("sort_order", sa.Integer),
        schema=_SCHEMA,
    )
    engines = sa.Table(
        "engines",
        metadata,
        sa.Column("id", sa.Integer),
        sa.Column("engine_kind", sa.String),
        sa.Column("name", sa.String),
        sa.Column("status", sa.String),
        sa.Column("connection_config", sa.JSON),
        sa.Column("deployment_config", sa.JSON),
        schema=_SCHEMA,
    )
    channels = sa.Table(
        "notification_channels",
        metadata,
        sa.Column("id", sa.Integer),
        sa.Column("channel_kind", sa.String),
        sa.Column("subtitle", sa.String),
        sa.Column("config", sa.JSON),
        schema=_SCHEMA,
    )
    return plans, engines, channels


def _plan_catalog() -> list[dict[str, Any]]:
    return [
        {
            "code": "free",
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
            "code": "pro",
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
            "code": "team",
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


def _engine_catalog() -> list[dict[str, Any]]:
    return [
        {
            "engine_kind": "freqtrade",
            "name": "Freqtrade 执行引擎",
            "status": "stopped",
            "connection_config": {
                "orchestratorUrl": "http://freqtrade-orchestrator:8090",
                "orchestratorToken": "",
                "instanceImage": "",
                "timeout": 30,
            },
            "deployment_config": {"logLevel": "INFO", "scheduler": 8},
        },
        {
            "engine_kind": "tradingagents",
            "name": "TradingAgents API 服务",
            "status": "stopped",
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
    ]


def _insert_missing_catalogs(plans: sa.Table, engines: sa.Table) -> None:
    bind = op.get_bind()
    for item in _plan_catalog():
        exists = bind.execute(sa.select(plans.c.id).where(plans.c.code == item["code"])).scalar_one_or_none()
        if exists is None:
            bind.execute(plans.insert().values(**item))
    for item in _engine_catalog():
        exists = bind.execute(
            sa.select(engines.c.id).where(engines.c.engine_kind == item["engine_kind"])
        ).scalar_one_or_none()
        if exists is None:
            bind.execute(engines.insert().values(**item))


def _encrypt_config(
    config: dict[str, Any], keys: frozenset[str], fernet: Fernet | None
) -> dict[str, Any]:
    encrypted = dict(config)
    if fernet is None:
        return encrypted
    for key in keys:
        value = encrypted.get(key)
        if not isinstance(value, str) or not value or value.startswith(_CIPHER_PREFIX):
            continue
        token = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        encrypted[key] = f"{_CIPHER_PREFIX}{token}"
    return encrypted


def _fernet_for_legacy_rows(has_legacy: bool) -> Fernet | None:
    if not has_legacy:
        return None
    key = (get_settings().ENCRYPT_KEY or "").strip()
    if not key:
        raise RuntimeError("检测到历史明文敏感配置；执行 0004 迁移前必须设置 ENCRYPT_KEY")
    try:
        return Fernet(key.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("ENCRYPT_KEY 不是有效的 Fernet 密钥，无法迁移历史敏感配置") from exc


def _has_plaintext(config: dict[str, Any], keys: frozenset[str]) -> bool:
    return any(
        isinstance(config.get(key), str)
        and bool(config[key])
        and not str(config[key]).startswith(_CIPHER_PREFIX)
        for key in keys
    )


def _encrypt_legacy_configs(engines: sa.Table, channels: sa.Table) -> None:
    bind = op.get_bind()
    engine_rows = list(bind.execute(sa.select(engines.c.id, engines.c.connection_config)).mappings())
    channel_rows = list(
        bind.execute(
            sa.select(channels.c.id, channels.c.channel_kind, channels.c.subtitle, channels.c.config)
        ).mappings()
    )
    has_legacy = any(
        _has_plaintext(dict(row["connection_config"] or {}), _ENGINE_SECRET_KEYS) for row in engine_rows
    ) or any(_has_plaintext(dict(row["config"] or {}), _NOTIFICATION_SECRET_KEYS) for row in channel_rows)
    fernet = _fernet_for_legacy_rows(has_legacy)

    for row in engine_rows:
        config = dict(row["connection_config"] or {})
        encrypted = _encrypt_config(config, _ENGINE_SECRET_KEYS, fernet)
        if encrypted != config:
            bind.execute(engines.update().where(engines.c.id == row["id"]).values(connection_config=encrypted))

    private_kinds = {"lark", "discord", "webhook"}
    for row in channel_rows:
        config = dict(row["config"] or {})
        encrypted = _encrypt_config(config, _NOTIFICATION_SECRET_KEYS, fernet)
        values: dict[str, Any] = {"config": encrypted}
        if row["channel_kind"] in private_kinds and (config.get("url") or config.get("webhookUrl")):
            values["subtitle"] = "notif.chConfigured"
        subtitle_changed = "subtitle" in values and values["subtitle"] != row["subtitle"]
        if encrypted != config or subtitle_changed:
            bind.execute(channels.update().where(channels.c.id == row["id"]).values(**values))


def upgrade() -> None:
    plans, engines, channels = _tables()
    _insert_missing_catalogs(plans, engines)
    _encrypt_legacy_configs(engines, channels)


def downgrade() -> None:
    # 不删除可能已被运营修改的目录，也不把密文降级回明文。
    pass
