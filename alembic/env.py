"""Alembic 迁移环境（异步 psycopg）。

数据库地址从应用配置读取（与运行时同源），目标 metadata 为 Base.metadata；
``import models`` 触发全部表注册，autogenerate 才能看到完整 schema。
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.schema import CreateSchema

import models  # noqa: F401 — 触发 models 包内所有子模块的 SQLAlchemy 表注册
from configs import get_settings
from libs.ctrl.db.sqlalchemy import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return get_settings().DATABASE_URL.strip()


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL 脚本，不连库。"""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=target_metadata.schema,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    schema = target_metadata.schema
    if schema and schema != "public":
        connection.execute(CreateSchema(schema, if_not_exists=True))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=schema,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
        await connection.commit()
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
