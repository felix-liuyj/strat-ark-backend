"""补齐 Stripe 集成在既有表上新增的列。

基线 0001 用 create_all(checkfirst=True) 建表：对已存在的表是空操作，因此
早于 Stripe 集成（59547aa / f0a4a06）建库的环境缺以下列，登录等查询直接 500：

- users.stripe_customer_id（含索引）
- plans.stripe_product_id / stripe_price_monthly_id / stripe_price_yearly_id
- subscriptions.stripe_subscription_id（含索引）
- invoices.external_url

全部用 IF NOT EXISTS 幂等补列：新库（baseline 已含全量列）与手工补过列的库
均为空操作。列定义与 models/user.py、models/subscription.py 逐一对齐。

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10
"""

from collections.abc import Sequence

from alembic import op

from libs.ctrl.db.sqlalchemy import Base

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = Base.metadata.schema or "public"


def _table(name: str) -> str:
    return f'"{_SCHEMA}"."{name}"'


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_table('users')} ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(64)")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_users_stripe_customer_id ON {_table('users')} (stripe_customer_id)"
    )

    op.execute(f"ALTER TABLE {_table('plans')} ADD COLUMN IF NOT EXISTS stripe_product_id VARCHAR(64)")
    op.execute(f"ALTER TABLE {_table('plans')} ADD COLUMN IF NOT EXISTS stripe_price_monthly_id VARCHAR(64)")
    op.execute(f"ALTER TABLE {_table('plans')} ADD COLUMN IF NOT EXISTS stripe_price_yearly_id VARCHAR(64)")

    op.execute(
        f"ALTER TABLE {_table('subscriptions')} ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(64)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_subscriptions_stripe_subscription_id"
        f" ON {_table('subscriptions')} (stripe_subscription_id)"
    )

    op.execute(f"ALTER TABLE {_table('invoices')} ADD COLUMN IF NOT EXISTS external_url VARCHAR(512)")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_table('invoices')} DROP COLUMN IF EXISTS external_url")
    op.execute(f'DROP INDEX IF EXISTS "{_SCHEMA}".ix_subscriptions_stripe_subscription_id')
    op.execute(f"ALTER TABLE {_table('subscriptions')} DROP COLUMN IF EXISTS stripe_subscription_id")
    op.execute(f"ALTER TABLE {_table('plans')} DROP COLUMN IF EXISTS stripe_price_yearly_id")
    op.execute(f"ALTER TABLE {_table('plans')} DROP COLUMN IF EXISTS stripe_price_monthly_id")
    op.execute(f"ALTER TABLE {_table('plans')} DROP COLUMN IF EXISTS stripe_product_id")
    op.execute(f'DROP INDEX IF EXISTS "{_SCHEMA}".ix_users_stripe_customer_id')
    op.execute(f"ALTER TABLE {_table('users')} DROP COLUMN IF EXISTS stripe_customer_id")
