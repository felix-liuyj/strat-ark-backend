"""回测中心请求表单。"""

from fastapi import Body

from libs.schema import ApiFormModel

__all__ = ("BacktestCreateForm",)


class BacktestCreateForm(ApiFormModel):
    """创建回测任务（策略 / 交易对 / 周期 / 时间范围 / 资金 / 手续费 / 滑点）。"""

    strategyId: int | None = Body(None, embed=True, description="策略 ID（可空，按名称回测）")
    strategyName: str = Body(..., embed=True, description="策略名称")
    symbol: str = Body(..., embed=True, description="交易对，如 BTC/USDT")
    timeframe: str = Body("1h", embed=True, description="周期，如 1h / 15m / 4h / 1d")
    startDate: str = Body(..., embed=True, description="回测开始日期")
    endDate: str = Body(..., embed=True, description="回测结束日期")
    initialBalance: float = Body(10000.0, embed=True, description="初始资金（USDT）")
    feeRate: float = Body(0.0004, embed=True, description="手续费率（小数，0.0004 = 0.04%）")
    slippageRate: float = Body(0.0005, embed=True, description="滑点率（小数，0.0005 = 0.05%）")
