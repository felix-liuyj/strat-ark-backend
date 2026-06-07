"""交易记录请求表单。

交易记录 / 持仓 / 订单以查询为主，筛选参数走路由 Query（snake_case），此处仅定义
需要请求体的写操作（取消挂单）。Body 字段一律 camelCase。
"""

from fastapi import Body

from libs.schema import ApiFormModel

__all__ = ("CancelOrderForm",)


class CancelOrderForm(ApiFormModel):
    """取消未完成订单（可选附带取消原因）。"""

    reason: str | None = Body(None, embed=True, description="取消原因")
