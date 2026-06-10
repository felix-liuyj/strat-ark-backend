"""Donchian Breakout —— 平台内置突破策略（对应 strategies 表 freqtrade_class）。

唐奇安通道突破 + ATR 过滤：收盘突破 N 周期高点且波动充分时入场，跌破通道中轨离场。
参数与平台 Strategy 表 params 对齐：Channel 20 / ATR Period 14 / ATR Mult 1.5。
"""

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy


class DonchianBreakout(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 50

    minimal_roi = {"0": 0.12, "240": 0.06, "720": 0.03}
    stoploss = -0.08
    trailing_stop = True
    trailing_stop_positive = 0.02

    channel_period = IntParameter(10, 40, default=20, space="buy")
    atr_period = IntParameter(7, 21, default=14, space="buy")
    atr_mult = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        period = int(self.channel_period.value)
        dataframe["dc_upper"] = dataframe["high"].rolling(period).max()
        dataframe["dc_lower"] = dataframe["low"].rolling(period).min()
        dataframe["dc_middle"] = (dataframe["dc_upper"] + dataframe["dc_lower"]) / 2
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=int(self.atr_period.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["dc_upper"].shift(1))
                & (dataframe["atr"] * float(self.atr_mult.value) < dataframe["close"] * 0.05)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["close"] < dataframe["dc_middle"]), "exit_long"] = 1
        return dataframe
