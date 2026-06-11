"""导航菜单聚合响应模型。"""

from pydantic import Field

from libs.schema import ApiResponseModel

__all__ = ("NavigationCountsResponseData",)


class NavigationCountsResponseData(ApiResponseModel):
    """侧边导航菜单计数。"""

    signals: int = Field(..., description="待处理信号数量")
    bots: int = Field(..., description="运行中机器人数量")
    notifications: int = Field(..., description="未读通知数量")
