"""交易记录 / 持仓 / 订单 ORM 模型及枚举。

覆盖交易记录（开仓 / 平仓 / 盈亏 / 时长 / 价格 / 方向）、持仓（开仓价 / 现价 / 数量 /
持仓价值 / 未实现盈亏）、未完成订单（挂单）。绑定关系不用 ORM relationship，
跨模块用字符串外键。
"""

from enum import StrEnum

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "Order",
    "OrderStatusEnum",
    "OrderTypeEnum",
    "Position",
    "Trade",
    "TradeSideEnum",
    "TradeStatusEnum",
)


class TradeSideEnum(StrEnum):
    """交易方向（与前端 Long / Short 对齐）。"""

    LONG = "long"
    SHORT = "short"


class TradeStatusEnum(StrEnum):
    """交易状态（持仓中 / 已平仓）。"""

    OPEN = "open"
    CLOSED = "closed"


class OrderTypeEnum(StrEnum):
    """订单类型。"""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatusEnum(StrEnum):
    """订单状态（未完成订单聚焦 pending / partial）。"""

    PENDING = "pending"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELED = "canceled"


class Trade(Base, TimestampMixin):
    """单条交易记录（开仓 / 平仓 / 盈亏 / 时长）。"""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # 外部交易引用号（Freqtrade / 交易所成交 id），便于幂等回写。
    trade_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, default=None)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    side: Mapped[TradeSideEnum] = mapped_column(String(10), nullable=False, default=TradeSideEnum.LONG)
    status: Mapped[TradeStatusEnum] = mapped_column(
        String(10), nullable=False, default=TradeStatusEnum.OPEN, index=True
    )
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bots.id"), nullable=True, default=None)
    bot_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    open_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 时长文案（持仓中显示「持仓中」），与前端一致直接存展示串。
    duration: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    opened_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    closed_at: Mapped[str | None] = mapped_column(String(40), nullable=True, default=None)


class Position(Base, TimestampMixin):
    """单个持仓快照（开仓价 / 现价 / 数量 / 持仓价值 / 未实现盈亏）。"""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    position_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, default=None)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    side: Mapped[TradeSideEnum] = mapped_column(String(10), nullable=False, default=TradeSideEnum.LONG)
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bots.id"), nullable=True, default=None)
    bot_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    open_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    position_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class Order(Base, TimestampMixin):
    """未完成订单（挂单）。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    order_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, default=None)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    side: Mapped[TradeSideEnum] = mapped_column(String(10), nullable=False, default=TradeSideEnum.LONG)
    order_type: Mapped[OrderTypeEnum] = mapped_column(String(10), nullable=False, default=OrderTypeEnum.LIMIT)
    status: Mapped[OrderStatusEnum] = mapped_column(
        String(10), nullable=False, default=OrderStatusEnum.PENDING, index=True
    )
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bots.id"), nullable=True, default=None)
    bot_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    filled_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at_label: Mapped[str] = mapped_column(String(40), nullable=False, default="")
