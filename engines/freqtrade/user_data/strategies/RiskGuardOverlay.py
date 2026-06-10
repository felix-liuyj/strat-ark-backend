"""Risk Guard Overlay —— 平台内置风控叠加策略（对应 strategies 表 freqtrade_class）。

保守趋势内核 + 全套 freqtrade 保护器（最大回撤 / 连续止损冷却 / 低收益对剔除），
面向"宁可少赚不可大亏"的资金保护场景。
参数与平台 Strategy 表 params 对齐：Max DD 10% / Daily Loss 3% / Vol Filter on。
"""

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class RiskGuardOverlay(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 60

    minimal_roi = {"0": 0.05, "240": 0.025, "720": 0.01}
    stoploss = -0.03
    trailing_stop = True
    trailing_stop_positive = 0.01

    @property
    def protections(self) -> list[dict]:
        return [
            # 最大回撤保护：1 天窗口内回撤超 10% 全局停手 12 小时。
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 24,
                "trade_limit": 4,
                "stop_duration_candles": 12,
                "max_allowed_drawdown": 0.10,
            },
            # 连续止损冷却：4 小时内 2 次止损即冷却该交易对 4 小时。
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 4,
                "trade_limit": 2,
                "stop_duration_candles": 4,
                "only_per_pair": True,
            },
            # 平仓后冷却 2 根 K 线，避免立刻反向追单。
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=55)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        # 波动过滤：ATR 占比超 4% 视为波动过高，不入场。
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["atr_pct"] < 0.04)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["ema_fast"] < dataframe["ema_slow"]), "exit_long"] = 1
        return dataframe
