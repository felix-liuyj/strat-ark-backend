"""AI 投研请求表单。"""

from fastapi import Body

from libs.schema import ApiFormModel

__all__ = (
    "BacktestReviewForm",
    "MarketAnalysisForm",
    "SignalReviewForm",
)


class MarketAnalysisForm(ApiFormModel):
    """市场分析：指定交易对与周期，触发多智能体分析。"""

    symbol: str = Body(..., embed=True, description="交易对，如 BTC/USDT")
    timeframe: str = Body("1h", embed=True, description="周期，如 15m / 1h / 4h / 1d")


class SignalReviewForm(ApiFormModel):
    """信号复核：对指定信号发起多智能体复核。"""

    signalId: int = Body(..., embed=True, description="待复核的信号 ID")


class BacktestReviewForm(ApiFormModel):
    """回测复盘：对指定回测任务发起多智能体复盘。"""

    backtestTaskId: int = Body(..., embed=True, description="待复盘的回测任务 ID")
