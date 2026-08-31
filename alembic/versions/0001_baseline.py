"""基线：以当前 ORM 全量建表（空库），既有库等价空操作。

此前 schema 由 init_db() 的 create_all 提供；本基线把同一份 metadata 纳入 Alembic
版本管理：全新库 `alembic upgrade head` 即可完整建表，已由 create_all 建过表的库
（checkfirst）不做任何变更。此后所有 schema 演进必须走
`alembic revision --autogenerate -m "描述"` + `alembic upgrade head`，
应用启动不再跑 ALTER。

Revision ID: 0001
Revises:
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import models  # noqa: F401 — 触发全部表注册
from alembic import op
from libs.ctrl.db.sqlalchemy import Base

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
