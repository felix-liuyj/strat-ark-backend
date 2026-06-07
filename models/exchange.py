"""交易所账户 ORM 模型与枚举。

API Key/Secret 加密存储（stub：仅保存掩码 + 占位密文），任何接口都不明文回显。
归属字段 user_id 关联 users 表，删除用户级联删除其交易所账户。
"""

from enum import StrEnum

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "ExchangeAccount",
    "ExchangePermissionEnum",
    "ExchangeProviderEnum",
    "ExchangeStatusEnum",
)


class ExchangeProviderEnum(StrEnum):
    """支持的交易所（与前端 Binance / Bybit / OKX 对齐，OKX 即将开放）。"""

    BINANCE = "binance"
    BYBIT = "bybit"
    OKX = "okx"


class ExchangeStatusEnum(StrEnum):
    """交易所连接状态。"""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class ExchangePermissionEnum(StrEnum):
    """API Key 授权范围（前端展示 读取 / 交易）。"""

    READ_ONLY = "read_only"
    READ_TRADE = "read_trade"
    READ_TRADE_WITHDRAW = "read_trade_withdraw"


class ExchangeAccount(Base, TimestampMixin):
    """单个交易所账户（一个用户可绑定多个）。"""

    __tablename__ = "exchange_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    provider: Mapped[ExchangeProviderEnum] = mapped_column(String(20), nullable=False)
    status: Mapped[ExchangeStatusEnum] = mapped_column(
        String(20), nullable=False, default=ExchangeStatusEnum.CONNECTED
    )
    permission: Mapped[ExchangePermissionEnum] = mapped_column(
        String(30), nullable=False, default=ExchangePermissionEnum.READ_TRADE
    )

    # API 凭证加密存储（stub）：仅保存掩码供展示，密文为占位符；绝不明文回显。
    api_key_mask: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    api_secret_cipher: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    ip_whitelist: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 安全检查项位（前端绿勾 / 琥珀告警）。
    withdraw_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ip_whitelist_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trade_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 余额缓存（折合 USDT），由同步余额动作刷新。
    balance_usdt: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_synced_at: Mapped[str | None] = mapped_column(String(40), nullable=True, default=None)
