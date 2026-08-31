"""StratArk 策舟 · Freqtrade 示例策略（最小可运行起点）。

仅作为引擎首次拉起的占位策略：纯 pandas 实现的 SMA 快慢线交叉，不依赖
talib，便于官方镜像内直接加载。真实策略由 StratArk 策略库（前端策略实验室
导入 / 编辑）下发，运维替换 strategies/ 目录下的 .py 即可。

风控以平台风控规则 + config.json 兜底为准；本文件仅给出最简入场/出场信号。
"""

from __future__ import annotations

from typing import ClassVar

from freqtrade.strategy import IStrategy
from pandas import DataFrame


class SampleStrategy(IStrategy):
    """SMA 快慢线交叉示例：快线上穿慢线入场，下穿出场。"""

    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False

    # 与 config.json 双层约束，策略层给出更保守的兜底。
    minimal_roi: ClassVar[dict[str, float]] = {"0": 0.04, "60": 0.02, "120": 0.01, "240": 0.0}
    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 50

    fast_window = 12
    slow_window = 26

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma_fast"] = dataframe["close"].rolling(self.fast_window).mean()
        dataframe["sma_slow"] = dataframe["close"].rolling(self.slow_window).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        prev_fast = dataframe["sma_fast"].shift(1)
        prev_slow = dataframe["sma_slow"].shift(1)
        crossed_up = (prev_fast <= prev_slow) & (dataframe["sma_fast"] > dataframe["sma_slow"])
        dataframe.loc[crossed_up, "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        prev_fast = dataframe["sma_fast"].shift(1)
        prev_slow = dataframe["sma_slow"].shift(1)
        crossed_down = (prev_fast >= prev_slow) & (dataframe["sma_fast"] < dataframe["sma_slow"])
        dataframe.loc[crossed_down, "exit_long"] = 1
        return dataframe
