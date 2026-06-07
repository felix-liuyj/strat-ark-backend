"""行情自选 ORM 模型。

行情数据本身（ticker / K 线 / 订单簿 / 成交流 / 热力图）全部来自交易所行情
service stub，不落库；唯一需要持久化的是「用户自选交易对」。该模型支撑自选列表的
增删与展示，行情数值在查询时由 service 实时填充。绑定关系不用 ORM relationship。
"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = ("MarketWatchlistItem",)


class MarketWatchlistItem(Base, TimestampMixin):
    """用户自选交易对（同一用户同一交易对唯一）。"""

    __tablename__ = "market_watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_watchlist_user_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # 现货 / 合约分类（前端 Watchlist chips 过滤用）。
    market_type: Mapped[str] = mapped_column(String(20), nullable=False, default="spot")
