"""通知与通知渠道 API 路由。"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.notification import (
    NotificationChannelCreateForm,
    NotificationChannelUpdateForm,
    NotificationCreateForm,
    NotificationSubscriptionUpdateForm,
)
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.notification import (
    NotificationChannelResponseData,
    NotificationListResponseData,
    NotificationResponseData,
    NotificationSubscriptionResponseData,
    NotificationTestResponseData,
)
from view_models.notification import (
    CreateNotificationChannelViewModel,
    CreateNotificationViewModel,
    DeleteNotificationChannelViewModel,
    GetNotificationSubscriptionsViewModel,
    ListNotificationChannelsViewModel,
    ListNotificationsViewModel,
    MarkAllNotificationsReadViewModel,
    MarkNotificationReadViewModel,
    SendChannelTestViewModel,
    UpdateNotificationChannelViewModel,
    UpdateNotificationSubscriptionsViewModel,
)

__all__ = ("router",)

router = APIRouter()

_TAGS = ["StratArk/通知中心"]


@router.get(
    "/notifications",
    response_model=BaseResponseModel[NotificationListResponseData],
    summary="获取通知信息流",
    description="返回当前用户的站内通知与未读数，支持按类型筛选与仅看未读。",
    tags=_TAGS,
)
async def list_notifications(
    request: Request,
    notif_type: str | None = Query(None, description="通知类型筛选"),
    unread_only: bool = Query(False, description="仅看未读"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        ListNotificationsViewModel,
        request,
        db,
        checker=checker,
        notif_type=notif_type,
        unread_only=unread_only,
    )


@router.post(
    "/notifications",
    response_model=BaseResponseModel[NotificationResponseData],
    summary="创建通知",
    description="为当前用户创建一条站内通知（系统触发 / 联调用）。",
    tags=_TAGS,
)
async def create_notification(
    request: Request,
    form: NotificationCreateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateNotificationViewModel, request, db, checker=checker, form=form)


@router.post(
    "/notifications/{notification_id}/read",
    response_model=BaseResponseModel[NotificationResponseData],
    summary="标记通知已读",
    description="将指定通知标记为已读。",
    tags=_TAGS,
)
async def mark_notification_read(
    request: Request,
    notification_id: int,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        MarkNotificationReadViewModel, request, db, checker=checker, notification_id=notification_id
    )


@router.post(
    "/notifications/read-all",
    response_model=BaseResponseModel[dict],
    summary="全部标记已读",
    description="将当前用户的全部未读通知标记为已读。",
    tags=_TAGS,
)
async def mark_all_notifications_read(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(MarkAllNotificationsReadViewModel, request, db, checker=checker)


@router.get(
    "/notification-channels",
    response_model=BaseResponseModel[list[NotificationChannelResponseData]],
    summary="获取渠道配置列表",
    description="返回当前用户的全部通知渠道配置，敏感字段已掩码。",
    tags=_TAGS,
)
async def list_notification_channels(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListNotificationChannelsViewModel, request, db, checker=checker)


@router.post(
    "/notification-channels",
    response_model=BaseResponseModel[NotificationChannelResponseData],
    summary="新增渠道配置",
    description="为当前用户新增一个通知渠道配置（每渠道类型唯一）。",
    tags=_TAGS,
)
async def create_notification_channel(
    request: Request,
    form: NotificationChannelCreateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateNotificationChannelViewModel, request, db, checker=checker, form=form)


@router.put(
    "/notification-channels/{channel_id}",
    response_model=BaseResponseModel[NotificationChannelResponseData],
    summary="更新渠道配置",
    description="更新指定渠道配置的字段与开关，掩码占位字段不会覆盖已存敏感值。",
    tags=_TAGS,
)
async def update_notification_channel(
    request: Request,
    channel_id: int,
    form: NotificationChannelUpdateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        UpdateNotificationChannelViewModel, request, db, checker=checker, channel_id=channel_id, form=form
    )


@router.delete(
    "/notification-channels/{channel_id}",
    response_model=BaseResponseModel[dict],
    summary="删除渠道配置",
    description="删除当前用户的指定通知渠道配置。",
    tags=_TAGS,
)
async def delete_notification_channel(
    request: Request,
    channel_id: int,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        DeleteNotificationChannelViewModel, request, db, checker=checker, channel_id=channel_id
    )


@router.post(
    "/notification-channels/{channel_id}/test",
    response_model=BaseResponseModel[NotificationTestResponseData],
    summary="发送渠道测试",
    description="向指定渠道发送一条真实测试通知；未接入发送网关的渠道返回明确失败。",
    tags=_TAGS,
)
async def send_channel_test(
    request: Request,
    channel_id: int,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        SendChannelTestViewModel, request, db, checker=checker, channel_id=channel_id
    )


@router.get(
    "/notification-subscriptions",
    response_model=BaseResponseModel[list[NotificationSubscriptionResponseData]],
    summary="获取订阅矩阵",
    description="返回当前用户的事件 × 渠道订阅矩阵。",
    tags=_TAGS,
)
async def get_notification_subscriptions(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetNotificationSubscriptionsViewModel, request, db, checker=checker)


@router.put(
    "/notification-subscriptions",
    response_model=BaseResponseModel[dict],
    summary="更新订阅矩阵",
    description="批量更新事件 × 渠道订阅矩阵单元格开关。",
    tags=_TAGS,
)
async def update_notification_subscriptions(
    request: Request,
    form: NotificationSubscriptionUpdateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        UpdateNotificationSubscriptionsViewModel, request, db, checker=checker, form=form
    )
