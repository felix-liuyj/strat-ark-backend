"""SQLAlchemy engine, session, declarative base and mixins."""

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import CreateSchema
from sqlalchemy.sql import Executable

from configs import get_settings

__all__ = (
    "AsyncSession",
    "Base",
    "TimestampMixin",
    "engine",
    "get_db",
    "init_db",
    "scalars_all",
    "scalars_first",
)
POSTGRESQL_DRIVER_PREFIX = "postgresql+psycopg://"


def _get_database_url() -> str:
    url = get_settings().DATABASE_URL.strip()
    if not url.startswith(POSTGRESQL_DRIVER_PREFIX):
        raise RuntimeError(f"DATABASE_URL must use {POSTGRESQL_DRIVER_PREFIX}")
    return url


def _make_engine() -> AsyncEngine:
    # pool_pre_ping: 借用连接前发 SELECT 1,检测到 PG AdminShutdown/IdleTimeout
    # 等已断开情况时,自动丢弃并重建,避免 psycopg.errors.AdminShutdown 抛到业务层
    # pool_recycle: 连接最长存活 30 分钟,早于常见的 idle_in_transaction_session_timeout
    return create_async_engine(
        _get_database_url(),
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def _get_default_schema() -> str | None:
    schema = (get_settings().DATABASE_SCHEMA or "").strip()
    return schema or None


engine = _make_engine()

_SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    metadata = MetaData(schema=_get_default_schema())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with _SessionLocal() as db:
        yield db


def new_async_session() -> AsyncSession:
    """在请求生命周期之外新开一个独立 AsyncSession。

    供 FastAPI BackgroundTasks 等脱离请求依赖注入的后台逻辑使用 —— 请求级 ``get_db``
    会话在响应返回后即关闭,后台任务必须持有自己的会话并显式 ``commit``。
    用法: ``async with new_async_session() as db: ...``。
    """
    return _SessionLocal()


async def _ensure_schema_exists_async() -> None:
    schema = _get_default_schema()
    if schema is None or schema == "public":
        return
    async with engine.begin() as connection:
        await connection.execute(CreateSchema(schema, if_not_exists=True))


# 多 worker(gunicorn/uvicorn 多进程)并发启动时,建表 + schema 兼容 ALTER 都是 DDL(需
# AccessExclusiveLock),并发执行会互相死锁(worker A 持表1锁等表2、worker B 持表2锁等表1 →
# "deadlock detected" → Application startup failed)。用 PG **会话级 advisory lock** 把整段
# 初始化串行化:同一时刻只有一个 worker 跑 DDL/seed,其余阻塞等待,待其完成后再跑(此时
# CREATE/ALTER ... IF NOT EXISTS 均为空操作)。lock 在连接关闭/进程退出时自动释放,不会卡死。
_INIT_DB_ADVISORY_LOCK_KEY = 4781921  # 固定 key,跨 worker 一致即可


async def init_db() -> None:
    """建表;多 worker 启动用 PG advisory lock 串行化,避免 DDL 死锁。"""
    import models  # noqa: F401 — 触发 models 包内所有子模块的 SQLAlchemy 表注册

    await _ensure_schema_exists_async()
    async with engine.connect() as lock_conn:
        # 阻塞直到取得 advisory lock(其它 worker 正在初始化时在此等待),取得后独占执行下面的 DDL。
        await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _INIT_DB_ADVISORY_LOCK_KEY})
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _INIT_DB_ADVISORY_LOCK_KEY})


async def scalars_all(db: AsyncSession, statement: Executable) -> list[Any]:
    return list((await db.scalars(statement)).all())


async def scalars_first(db: AsyncSession, statement: Executable) -> Any | None:
    return (await db.scalars(statement)).first()
