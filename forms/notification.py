"""通知与通知渠道请求表单。"""

from typing import Any

from fastapi import Body

from libs.schema import ApiFormModel
from models.notification import ChannelKindEnum, NotificationTypeEnum

__all__ = (
    "NotificationChannelCreateForm",
    "NotificationChannelUpdateForm",
    "NotificationCreateForm",
    "NotificationSubscriptionUpdateForm",
    "SubscriptionItemForm",
)


class NotificationCreateForm(ApiFormModel):
    """创建一条站内通知（系统 / 管理触发，便于联调与回放）。"""

    notifType: NotificationTypeEnum = Body(..., embed=True, description="通知类型")
    title: str = Body(..., embed=True, description="标题")
    description: str = Body("", embed=True, description="描述")
    resource: str | None = Body(None, embed=True, description="关联资源名")
    resourceId: str | None = Body(None, embed=True, description="关联资源 ID")


class NotificationChannelCreateForm(ApiFormModel):
    """新增渠道配置。``config`` 按渠道类型存不同字段。"""

    channelKind: ChannelKindEnum = Body(..., embed=True, description="渠道类型")
    displayName: str = Body("", embed=True, description="渠道显示名")
    subtitle: str = Body("", embed=True, description="渠道副标题 / 绑定标识")
    isEnabled: bool = Body(False, embed=True, description="是否启用")
    config: dict[str, Any] = Body(default_factory=dict, embed=True, description="渠道专属配置")


class NotificationChannelUpdateForm(ApiFormModel):
    """更新渠道配置（按渠道类型字段不同，统一走 config）。"""

    displayName: str | None = Body(None, embed=True, description="渠道显示名")
    subtitle: str | None = Body(None, embed=True, description="渠道副标题 / 绑定标识")
    isEnabled: bool | None = Body(None, embed=True, description="是否启用")
    config: dict[str, Any] | None = Body(None, embed=True, description="渠道专属配置")


class SubscriptionItemForm(ApiFormModel):
    """订阅矩阵中的单格：某事件 × 某渠道的开关。"""

    eventKey: str = Body(..., embed=True, description="事件标识")
    channelKind: ChannelKindEnum = Body(..., embed=True, description="渠道类型")
    isEnabled: bool = Body(..., embed=True, description="是否开启")


class NotificationSubscriptionUpdateForm(ApiFormModel):
    """批量更新事件 × 渠道订阅矩阵。"""

    items: list[SubscriptionItemForm] = Body(..., embed=True, description="订阅矩阵单元格列表")
