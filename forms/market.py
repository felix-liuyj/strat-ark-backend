"""行情请求表单。

行情数据只读（走真实行情 service），唯一写操作是自选交易对的新增。删除走路由 Path。
Body 字段一律 camelCase。
"""

from fastapi import Body

from libs.schema import ApiFormModel

__all__ = ("WatchlistAddForm",)


class WatchlistAddForm(ApiFormModel):
    """新增自选交易对。"""

    symbol: str = Body(..., embed=True, description="交易对，如 BTC/USDT")
    marketType: str = Body("spot", embed=True, description="现货 spot / 合约 futures")
