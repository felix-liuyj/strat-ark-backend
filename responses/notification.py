"""通知与通知渠道响应模型。"""

from datetime import datetime
from typing import Any

from pydantic import Field

from libs.schema import ApiResponseModel
from models.notification import ChannelKindEnum, NotificationTypeEnum

__all__ = (
    "NotificationChannelResponseData",
    "NotificationListResponseData",
    "NotificationResponseData",
    "NotificationSubscriptionResponseData",
    "NotificationTestResponseData",
)


class NotificationResponseData(ApiResponseModel):
    id: int = Field(..., description="通知 ID")
    notifType: NotificationTypeEnum = Field(..., description="通知类型")
    title: str = Field(..., description="标题")
    description: str = Field(..., description="描述")
    isRead: bool = Field(..., description="是否已读")
    resource: str | None = Field(None, description="关联资源名")
    resourceId: str | None = Field(None, description="关联资源 ID")
    createdAt: datetime = Field(..., description="创建时间")


class NotificationListResponseData(ApiResponseModel):
    """通知信息流 + 未读数（前端筛选栏与未读角标共用）。"""

    unreadCount: int = Field(..., description="未读数量")
    items: list[NotificationResponseData] = Field(..., description="通知列表")


class NotificationChannelResponseData(ApiResponseModel):
    id: int = Field(..., description="渠道配置 ID")
    channelKind: ChannelKindEnum = Field(..., description="渠道类型")
    displayName: str = Field(..., description="渠道显示名")
    subtitle: str = Field(..., description="渠道副标题 / 绑定标识")
    isEnabled: bool = Field(..., description="是否启用")
    # 敏感字段已在 ViewModel 掩码后返回，不回显明文。
    config: dict[str, Any] = Field(..., description="渠道专属配置（敏感字段已掩码）")


class NotificationSubscriptionResponseData(ApiResponseModel):
    eventKey: str = Field(..., description="事件标识")
    channelKind: ChannelKindEnum = Field(..., description="渠道类型")
    isEnabled: bool = Field(..., description="是否开启")


class NotificationTestResponseData(ApiResponseModel):
    """渠道发送测试结果。"""

    ok: bool = Field(..., description="是否发送成功")
    channelKind: ChannelKindEnum = Field(..., description="渠道类型")
    message: str = Field(..., description="结果说明")
    latencyMs: int = Field(..., description="发送耗时（毫秒）")
