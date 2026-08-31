"""Mean Reversion BB —— 平台内置均值回归策略（对应 strategies 表 freqtrade_class）。

布林带下轨超卖回归：收盘跌破下轨且 RSI 超卖入场，回归中轨离场。
参数与平台 Strategy 表 params 对齐：BB Period 20 / BB Std 2.0 / RSI Period 14。
"""

from typing import ClassVar

import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame


class MeanReversionBB(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 40

    minimal_roi: ClassVar[dict[str, float]] = {"0": 0.04, "60": 0.02, "180": 0.01}
    stoploss = -0.05
    trailing_stop = False

    bb_period = IntParameter(14, 30, default=20, space="buy")
    bb_std = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="buy")
    rsi_period = IntParameter(7, 21, default=14, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        upper, middle, lower = ta.BBANDS(
            dataframe["close"],
            timeperiod=int(self.bb_period.value),
            nbdevup=float(self.bb_std.value),
            nbdevdn=float(self.bb_std.value),
        )
        dataframe["bb_upper"] = upper
        dataframe["bb_middle"] = middle
        dataframe["bb_lower"] = lower
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=int(self.rsi_period.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["bb_lower"])
                & (dataframe["rsi"] < 30)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["close"] >= dataframe["bb_middle"]), "exit_long"] = 1
        return dataframe
