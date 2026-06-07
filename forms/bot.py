"""交易机器人请求表单（camelCase Body）。

BotCreateForm 字段对齐 Bot Wizard 五步：基本信息 / 选择策略 / 交易对与参数 /
风控规则 / 确认（acknowledged 强确认）。运行模式默认 dry_run。
"""

from fastapi import Body

from libs.schema import ApiFormModel
from models.bot import BotRunModeEnum, BotTradeModeEnum

__all__ = (
    "BotCreateForm",
    "BotSettingsUpdateForm",
    "BotUpdateForm",
)


class BotCreateForm(ApiFormModel):
    name: str = Body(..., embed=True, description="Bot 名称")
    exchangeAccountId: int = Body(..., embed=True, description="交易所账户 ID")
    strategyId: int = Body(..., embed=True, description="策略 ID")
    tradeMode: BotTradeModeEnum = Body(BotTradeModeEnum.FUTURES, embed=True, description="交易模式：futures / spot")
    runMode: BotRunModeEnum = Body(BotRunModeEnum.DRY_RUN, embed=True, description="运行模式：dry_run（默认）/ live")
    pairs: list[str] = Body(..., embed=True, description="交易对列表，例如 ['BTC/USDT','ETH/USDT']")
    stakeCurrency: str = Body("USDT", embed=True, description="计价币种")
    stakeAmount: float = Body(1000.0, embed=True, description="单笔仓位金额")
    maxOpenTrades: int = Body(3, embed=True, description="最大持仓数")
    timeframe: str = Body("15m", embed=True, description="周期")
    stoploss: str = Body("-6%", embed=True, description="止损")
    trailingStop: str = Body("1.5%", embed=True, description="移动止损")
    dailyLossLimit: str = Body("3%", embed=True, description="单日最大亏损")
    maxDrawdownLimit: str = Body("10%", embed=True, description="最大回撤")
    maxPosition: str = Body("5%", embed=True, description="单笔最大仓位")
    maxLeverage: str = Body("3x", embed=True, description="最大杠杆")
    riskConfig: dict[str, bool] | None = Body(
        None, embed=True, description="风控开关：cooldown / newsFilter / volatilityFilter / autoStop"
    )
    acknowledged: bool = Body(..., embed=True, description="风险声明强确认（必须为 true 才能创建）")


class BotUpdateForm(ApiFormModel):
    """编辑策略参数（Bot Detail 编辑参数弹窗，需二次确认）。"""

    stakeAmount: float | None = Body(None, embed=True, description="单笔仓位金额")
    maxOpenTrades: int | None = Body(None, embed=True, description="最大持仓数")
    stoploss: str | None = Body(None, embed=True, description="止损")
    trailingStop: str | None = Body(None, embed=True, description="移动止损")
    timeframe: str | None = Body(None, embed=True, description="周期")
    tradeMode: BotTradeModeEnum | None = Body(None, embed=True, description="交易模式")


class BotSettingsUpdateForm(ApiFormModel):
    """Bot Settings 面板开关。"""

    telegramNotify: bool | None = Body(None, embed=True, description="Telegram 通知")
    autoStopOnError: bool | None = Body(None, embed=True, description="异常自动停机")
    aiSignalFilter: bool | None = Body(None, embed=True, description="AI 信号过滤")
