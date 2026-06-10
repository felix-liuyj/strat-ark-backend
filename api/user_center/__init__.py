"""用户中心域 API 路由：API Key / OAuth 绑定 / 会话 / 2FA。"""

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.user_center import BindOAuthForm, CreateApiKeyForm, UpdateTwoFactorForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from models.user_center import OAuthProviderEnum
from responses.user_center import (
    ApiKeyCreatedResponseData,
    ApiKeyResponseData,
    OAuthBindingResponseData,
    TwoFactorResponseData,
    TwoFactorSetupResponseData,
    UserSessionResponseData,
)
from view_models.user_center import (
    BindOAuthViewModel,
    CreateApiKeyViewModel,
    GetTwoFactorViewModel,
    SetupTwoFactorViewModel,
    ListApiKeysViewModel,
    ListOAuthBindingsViewModel,
    ListSessionsViewModel,
    LogoutAllSessionsViewModel,
    LogoutSessionViewModel,
    RevokeApiKeyViewModel,
    UnbindOAuthViewModel,
    UpdateTwoFactorViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/user/api-keys",
    response_model=BaseResponseModel[list[ApiKeyResponseData]],
    summary="获取平台 API Key 列表",
    description="返回当前用户的平台 API Key（仅掩码展示，不含明文）。",
    tags=["StratArk/用户中心"],
)
async def list_api_keys(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListApiKeysViewModel, request, db, checker=checker)


@router.post(
    "/user/api-keys",
    response_model=BaseResponseModel[ApiKeyCreatedResponseData],
    summary="创建平台 API Key",
    description="创建一个平台 API Key，明文密钥仅在本次响应返回一次，请前端提示用户立即保存。",
    tags=["StratArk/用户中心"],
)
async def create_api_key(
    request: Request,
    form: CreateApiKeyForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateApiKeyViewModel, request, db, checker=checker, form=form)


@router.post(
    "/user/api-keys/{key_id}/revoke",
    response_model=BaseResponseModel[None],
    summary="撤销平台 API Key",
    description="撤销指定 API Key，使用该密钥的程序将立即失去访问权限（保留记录用于审计）。",
    tags=["StratArk/用户中心"],
)
async def revoke_api_key(
    request: Request,
    key_id: int = Path(..., description="API Key ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(RevokeApiKeyViewModel, request, db, key_id=key_id, checker=checker)


@router.get(
    "/user/oauth-bindings",
    response_model=BaseResponseModel[list[OAuthBindingResponseData]],
    summary="获取第三方账号绑定",
    description="返回 google / microsoft / github / apple 四提供方的绑定状态（未绑定也占一项）。",
    tags=["StratArk/用户中心"],
)
async def list_oauth_bindings(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListOAuthBindingsViewModel, request, db, checker=checker)


@router.post(
    "/user/oauth-bindings/bind",
    response_model=BaseResponseModel[OAuthBindingResponseData],
    summary="绑定第三方账号",
    description="绑定指定第三方账号（service stub 模拟授权，不发起真实 OAuth 跳转）。",
    tags=["StratArk/用户中心"],
)
async def bind_oauth(
    request: Request,
    form: BindOAuthForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(BindOAuthViewModel, request, db, checker=checker, form=form)


@router.post(
    "/user/oauth-bindings/{provider}/unbind",
    response_model=BaseResponseModel[None],
    summary="解绑第三方账号",
    description="解绑指定第三方账号，请确保至少保留一种登录方式。",
    tags=["StratArk/用户中心"],
)
async def unbind_oauth(
    request: Request,
    provider: OAuthProviderEnum = Path(..., description="提供方：google / microsoft / github / apple"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(UnbindOAuthViewModel, request, db, provider=provider, checker=checker)


@router.get(
    "/user/sessions",
    response_model=BaseResponseModel[list[UserSessionResponseData]],
    summary="获取活跃会话",
    description="返回当前用户的活跃登录会话，当前设备置顶。",
    tags=["StratArk/用户中心"],
)
async def list_sessions(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListSessionsViewModel, request, db, checker=checker)


@router.post(
    "/user/sessions/{session_id}/logout",
    response_model=BaseResponseModel[None],
    summary="退出单个会话",
    description="退出指定会话（非当前设备），该设备需重新登录。",
    tags=["StratArk/用户中心"],
)
async def logout_session(
    request: Request,
    session_id: int = Path(..., description="会话 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        LogoutSessionViewModel, request, db, session_id=session_id, checker=checker
    )


@router.post(
    "/user/sessions/logout-all",
    response_model=BaseResponseModel[None],
    summary="退出全部其它会话",
    description="登出除当前设备外的所有会话。",
    tags=["StratArk/用户中心"],
)
async def logout_all_sessions(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(LogoutAllSessionsViewModel, request, db, checker=checker)


@router.get(
    "/user/two-factor",
    response_model=BaseResponseModel[TwoFactorResponseData],
    summary="获取两步验证状态",
    description="返回当前用户的 2FA（TOTP）开关与实盘操作是否要求 2FA。",
    tags=["StratArk/用户中心"],
)
async def get_two_factor(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetTwoFactorViewModel, request, db, checker=checker)


@router.post(
    "/user/two-factor/setup",
    response_model=BaseResponseModel[TwoFactorSetupResponseData],
    summary="发起 TOTP 绑定",
    description="生成 TOTP secret 并返回 otpauth 绑定信息（扫码 / 手输录入 Authenticator）；"
    "需再调 PUT /user/two-factor 携带验证码确认后才真正启用。",
    tags=["StratArk/用户中心"],
)
async def setup_two_factor(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(SetupTwoFactorViewModel, request, db, checker=checker)


@router.put(
    "/user/two-factor",
    response_model=BaseResponseModel[TwoFactorResponseData],
    summary="更新两步验证设置",
    description="开启 / 关闭 TOTP（须携带验证码校验）或调整实盘操作是否要求 2FA。",
    tags=["StratArk/用户中心"],
)
async def update_two_factor(
    request: Request,
    form: UpdateTwoFactorForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(UpdateTwoFactorViewModel, request, db, checker=checker, form=form)
