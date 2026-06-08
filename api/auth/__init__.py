"""Authentication API routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.auth import (
    ChangePasswordForm,
    LoginForm,
    OAuthExchangeForm,
    RefreshTokenForm,
    RegisterForm,
    ResetPasswordForm,
    SendVerificationCodeForm,
    UpdateProfileForm,
)
from libs.auth.permissions import (
    PermissionChecker,
    get_permission_checker,
)
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.auth import AuthTokenResponseData, UserProfileResponseData
from view_models.auth import (
    ChangePasswordViewModel,
    GetCurrentUserViewModel,
    ListUsersViewModel,
    LoginViewModel,
    OAuthExchangeViewModel,
    RefreshTokenViewModel,
    RegisterViewModel,
    ResetPasswordViewModel,
    SendVerificationCodeViewModel,
    UpdateProfileViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.post(
    "/auth/otp",
    response_model=BaseResponseModel[None],
    summary="发送验证码",
    description="向指定邮箱发送注册或密码重置验证码，验证码有效期 5 分钟，60 秒内不可重复发送。",
    tags=["StratArk/认证 Auth"],
)
async def send_verification_code(
    request: Request,
    form: SendVerificationCodeForm,
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(SendVerificationCodeViewModel, request, db, form=form)


@router.post(
    "/auth/register",
    response_model=BaseResponseModel[AuthTokenResponseData],
    summary="注册账号",
    description="通过邮箱和验证码注册新账号，注册成功后直接返回访问令牌。",
    tags=["StratArk/认证 Auth"],
)
async def register(
    request: Request,
    form: RegisterForm,
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(RegisterViewModel, request, db, form=form)


@router.post(
    "/auth/login",
    response_model=BaseResponseModel[AuthTokenResponseData],
    summary="登录",
    description="通过邮箱和密码登录，返回访问令牌和刷新令牌。",
    tags=["StratArk/认证 Auth"],
)
async def login(
    request: Request,
    form: LoginForm,
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(LoginViewModel, request, db, form=form)


@router.post(
    "/oauth/exchange",
    response_model=BaseResponseModel[AuthTokenResponseData],
    summary="OAuth 登录授权码交换",
    description="使用前端 Public PKCE 流程得到的授权码换取自家访问令牌和刷新令牌。",
    tags=["StratArk/认证 Auth"],
)
async def exchange_oauth_code(
    request: Request,
    form: OAuthExchangeForm,
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(OAuthExchangeViewModel, request, db, form=form)


@router.post(
    "/auth/refresh",
    response_model=BaseResponseModel[AuthTokenResponseData],
    summary="刷新令牌",
    description="使用刷新令牌换取新的访问令牌。",
    tags=["StratArk/认证 Auth"],
)
async def refresh_token(
    request: Request,
    form: RefreshTokenForm,
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(RefreshTokenViewModel, request, db, form=form)


@router.post(
    "/auth/password/reset",
    response_model=BaseResponseModel[None],
    summary="重置密码",
    description="通过邮箱验证码重置账号密码。",
    tags=["StratArk/认证 Auth"],
)
async def reset_password(
    request: Request,
    form: ResetPasswordForm,
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ResetPasswordViewModel, request, db, form=form)


@router.put(
    "/auth/password",
    response_model=BaseResponseModel[None],
    summary="修改密码",
    description="登录状态下，通过旧密码验证后修改新密码。",
    tags=["StratArk/认证 Auth"],
)
async def change_password(
    request: Request,
    form: ChangePasswordForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ChangePasswordViewModel, request, db, checker=checker, form=form)


@router.get(
    "/auth/me",
    response_model=BaseResponseModel[UserProfileResponseData],
    summary="获取当前用户信息",
    description="获取当前登录用户的基本信息。",
    tags=["StratArk/认证 Auth"],
)
async def get_current_user(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetCurrentUserViewModel, request, db, checker=checker)


@router.put(
    "/auth/profile",
    response_model=BaseResponseModel[UserProfileResponseData],
    summary="更新用户资料",
    description="登录状态下更新显示名称和头像 URL。",
    tags=["StratArk/认证 Auth"],
)
async def update_profile(
    request: Request,
    form: UpdateProfileForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(UpdateProfileViewModel, request, db, checker=checker, form=form)


@router.get(
    "/admin/users",
    response_model=BaseResponseModel[list[UserProfileResponseData]],
    summary="管理员: 获取用户列表",
    description=(
        "仅管理员可调用。返回所有 is_active 用户摘要 (id / 邮箱 / 显示名 / 用户类型 / 头像), "
        "供 ProjectList 用户文件夹九宫格 + 所有用户弹窗消费。"
    ),
    tags=["StratArk/认证 Auth"],
)
async def list_users(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListUsersViewModel, request, db, checker=checker)
