"""交易机器人 ORM 模型与枚举（bots 表）。

对齐前端 Bots / Bot Detail / Bot Wizard：基本信息、交易模式、运行模式（默认 dry_run）、
绑定策略与交易所账户、交易对、仓位与执行参数、风控参数、各类开关。
交易 / 持仓 / 日志为运行时数据，统一由 libs.integrations.freqtrade 提供（config 驱动接真实引擎，
未配置时回退拟真数据），不落库。
"""

from enum import StrEnum

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.ctrl.db.sqlalchemy import Base, TimestampMixin

__all__ = (
    "Bot",
    "BotRunModeEnum",
    "BotStatusEnum",
    "BotTradeModeEnum",
)


class BotStatusEnum(StrEnum):
    """机器人运行状态（前端 Running / Stopped）。"""

    RUNNING = "running"
    STOPPED = "stopped"


class BotTradeModeEnum(StrEnum):
    """交易模式（前端 合约 Futures / 现货 Spot）。"""

    FUTURES = "futures"
    SPOT = "spot"


class BotRunModeEnum(StrEnum):
    """运行模式（前端 Dry-run 模拟盘 / Live 实盘）。默认 dry_run。"""

    DRY_RUN = "dry_run"
    LIVE = "live"


class Bot(Base, TimestampMixin):
    """单个交易机器人配置。"""

    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # RESTRICT：被 Bot 引用的交易所账户 / 策略不允许直接删除（删除入口先查引用并返回业务错误，
    # 数据库层兜底防止越过业务层的删除造成孤儿引用）。
    exchange_account_id: Mapped[int] = mapped_column(
        ForeignKey("exchange_accounts.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="RESTRICT"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    trade_mode: Mapped[BotTradeModeEnum] = mapped_column(
        String(20), nullable=False, default=BotTradeModeEnum.FUTURES
    )
    run_mode: Mapped[BotRunModeEnum] = mapped_column(
        String(20), nullable=False, default=BotRunModeEnum.DRY_RUN
    )
    status: Mapped[BotStatusEnum] = mapped_column(String(20), nullable=False, default=BotStatusEnum.STOPPED)

    # 交易对与执行参数。
    pairs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    stake_currency: Mapped[str] = mapped_column(String(20), nullable=False, default="USDT")
    stake_amount: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    max_open_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False, default="15m")
    stoploss: Mapped[str] = mapped_column(String(20), nullable=False, default="-6%")
    trailing_stop: Mapped[str] = mapped_column(String(20), nullable=False, default="1.5%")

    # 风控参数（前端风控规则步骤）。
    daily_loss_limit: Mapped[str] = mapped_column(String(20), nullable=False, default="3%")
    max_drawdown_limit: Mapped[str] = mapped_column(String(20), nullable=False, default="10%")
    max_position: Mapped[str] = mapped_column(String(20), nullable=False, default="5%")
    max_leverage: Mapped[str] = mapped_column(String(20), nullable=False, default="3x")
    risk_config: Mapped[dict[str, bool]] = mapped_column(JSON, nullable=False, default=dict)

    # 设置开关（前端 Settings 面板）。
    telegram_notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_stop_on_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ai_signal_filter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    live_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 运行时引用（容器编排），由 start/stop 写入。
    container_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    # 实例 REST API 访问信息：地址 + 随机生成的 api_server 凭证（密码 Fernet 加密）。
    api_url: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    api_username: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    api_password_cipher: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
