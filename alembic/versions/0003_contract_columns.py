"""修复历史 0002 歧义并补齐 live-bot 与 Stripe 契约列。

早期仓库曾存在两个 revision 都命名为 0002：一个补 live-bot 编排列，另一个补
Stripe 列。已有数据库即使显示已到 0002，也无法证明执行的是哪一个文件。本迁移
以当前 ORM 为准幂等检查两组列和索引，使全新库、任一旧 0002 状态及手工补列环境
最终收敛到同一 schema。

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from libs.ctrl.db.sqlalchemy import Base

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = Base.metadata.schema


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table, schema=_SCHEMA)}


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table, schema=_SCHEMA)}


def _repair_live_bot_columns() -> None:
    exchange_columns = _columns("exchange_accounts")
    if "api_key_cipher" not in exchange_columns:
        op.add_column(
            "exchange_accounts",
            sa.Column("api_key_cipher", sa.Text(), nullable=False, server_default=""),
            schema=_SCHEMA,
        )
    op.alter_column(
        "exchange_accounts",
        "api_secret_cipher",
        existing_type=sa.String(512),
        type_=sa.Text(),
        existing_nullable=False,
        schema=_SCHEMA,
    )

    bot_columns = _columns("bots")
    if "api_url" not in bot_columns:
        op.add_column("bots", sa.Column("api_url", sa.String(255), nullable=True), schema=_SCHEMA)
    if "api_username" not in bot_columns:
        op.add_column("bots", sa.Column("api_username", sa.String(64), nullable=True), schema=_SCHEMA)
    if "api_password_cipher" not in bot_columns:
        op.add_column("bots", sa.Column("api_password_cipher", sa.Text(), nullable=True), schema=_SCHEMA)

    if "freqtrade_class" not in _columns("strategies"):
        op.add_column(
            "strategies",
            sa.Column("freqtrade_class", sa.String(120), nullable=False, server_default=""),
            schema=_SCHEMA,
        )


def _add_stripe_columns() -> None:
    if "stripe_customer_id" not in _columns("users"):
        op.add_column("users", sa.Column("stripe_customer_id", sa.String(64), nullable=True), schema=_SCHEMA)
    if "ix_users_stripe_customer_id" not in _indexes("users"):
        op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"], schema=_SCHEMA)

    plan_columns = _columns("plans")
    for name in ("stripe_product_id", "stripe_price_monthly_id", "stripe_price_yearly_id"):
        if name not in plan_columns:
            op.add_column("plans", sa.Column(name, sa.String(64), nullable=True), schema=_SCHEMA)

    if "stripe_subscription_id" not in _columns("subscriptions"):
        op.add_column(
            "subscriptions",
            sa.Column("stripe_subscription_id", sa.String(64), nullable=True),
            schema=_SCHEMA,
        )
    if "ix_subscriptions_stripe_subscription_id" not in _indexes("subscriptions"):
        op.create_index(
            "ix_subscriptions_stripe_subscription_id",
            "subscriptions",
            ["stripe_subscription_id"],
            schema=_SCHEMA,
        )

    if "external_url" not in _columns("invoices"):
        op.add_column("invoices", sa.Column("external_url", sa.String(512), nullable=True), schema=_SCHEMA)


def upgrade() -> None:
    _repair_live_bot_columns()
    _add_stripe_columns()


def downgrade() -> None:
    if "external_url" in _columns("invoices"):
        op.drop_column("invoices", "external_url", schema=_SCHEMA)

    if "ix_subscriptions_stripe_subscription_id" in _indexes("subscriptions"):
        op.drop_index("ix_subscriptions_stripe_subscription_id", table_name="subscriptions", schema=_SCHEMA)
    if "stripe_subscription_id" in _columns("subscriptions"):
        op.drop_column("subscriptions", "stripe_subscription_id", schema=_SCHEMA)

    plan_columns = _columns("plans")
    for name in ("stripe_price_yearly_id", "stripe_price_monthly_id", "stripe_product_id"):
        if name in plan_columns:
            op.drop_column("plans", name, schema=_SCHEMA)

    if "ix_users_stripe_customer_id" in _indexes("users"):
        op.drop_index("ix_users_stripe_customer_id", table_name="users", schema=_SCHEMA)
    if "stripe_customer_id" in _columns("users"):
        op.drop_column("users", "stripe_customer_id", schema=_SCHEMA)
