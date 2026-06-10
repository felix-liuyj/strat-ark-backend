"""Live bot 编排：交易所凭证 Fernet 密文、bot 实例访问信息、策略 freqtrade 类名。

- exchange_accounts：新增 api_key_cipher（Text）；api_secret_cipher 放宽为 Text
  （Fernet 密文长度超过原 String(512)）。
- bots：新增实例 REST 访问信息 api_url / api_username / api_password_cipher。
- strategies：新增 freqtrade_class（IStrategy 类名映射，空表示无可执行实现）。

注意：基线 0001 是 create_all（全新库执行时本批列已随建表存在），故所有 add_column
都带存在性守卫，三种路径（旧库增量 / 新库基线 / create_all 兜底过的库）均幂等。

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    exchange_columns = _existing_columns("exchange_accounts")
    if "api_key_cipher" not in exchange_columns:
        op.add_column(
            "exchange_accounts",
            sa.Column("api_key_cipher", sa.Text(), nullable=False, server_default=""),
        )
        op.alter_column(
            "exchange_accounts",
            "api_secret_cipher",
            existing_type=sa.String(512),
            type_=sa.Text(),
            existing_nullable=False,
        )

    bot_columns = _existing_columns("bots")
    if "api_url" not in bot_columns:
        op.add_column("bots", sa.Column("api_url", sa.String(255), nullable=True))
        op.add_column("bots", sa.Column("api_username", sa.String(64), nullable=True))
        op.add_column("bots", sa.Column("api_password_cipher", sa.Text(), nullable=True))

    if "freqtrade_class" not in _existing_columns("strategies"):
        op.add_column(
            "strategies",
            sa.Column("freqtrade_class", sa.String(120), nullable=False, server_default=""),
        )


def downgrade() -> None:
    op.drop_column("strategies", "freqtrade_class")
    op.drop_column("bots", "api_password_cipher")
    op.drop_column("bots", "api_username")
    op.drop_column("bots", "api_url")
    op.alter_column(
        "exchange_accounts",
        "api_secret_cipher",
        existing_type=sa.Text(),
        type_=sa.String(512),
        existing_nullable=False,
    )
    op.drop_column("exchange_accounts", "api_key_cipher")
