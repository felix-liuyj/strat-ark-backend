"""Trend EMA RSI V1 —— 平台内置趋势策略（对应 strategies 表 freqtrade_class）。

EMA 快慢线多头排列 + RSI 阈值过滤的趋势跟随：快线上穿慢线且 RSI 高于阈值入场，
快线下穿慢线离场；硬止损与追踪止损由 bot 实例配置（FREQTRADE__* env）覆盖。
参数与平台 Strategy 表 params 对齐：EMA Fast 21 / EMA Slow 55 / RSI Period 14 / RSI Threshold 52。
"""

from typing import ClassVar

import talib.abstract as ta
from freqtrade.strategy import IntParameter, IStrategy
from pandas import DataFrame


class TrendEmaRsiV1(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "15m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 60

    minimal_roi: ClassVar[dict[str, float]] = {"0": 0.08, "120": 0.04, "360": 0.02}
    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.015

    ema_fast = IntParameter(13, 34, default=21, space="buy")
    ema_slow = IntParameter(34, 89, default=55, space="buy")
    rsi_period = IntParameter(7, 21, default=14, space="buy")
    rsi_threshold = IntParameter(45, 60, default=52, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=int(self.ema_fast.value))
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=int(self.ema_slow.value))
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=int(self.rsi_period.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["rsi"] > int(self.rsi_threshold.value))
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
            ),
            "exit_long",
        ] = 1
        return dataframe
