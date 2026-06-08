"""Authentication request forms."""

from enum import StrEnum

from fastapi import Body

from libs.schema import ApiFormModel

__all__ = (
    "ChangePasswordForm",
    "ForgotPasswordForm",
    "LoginForm",
    "OAuthExchangeForm",
    "OAuthLoginProviderEnum",
    "RefreshTokenForm",
    "RegisterForm",
    "ResetPasswordForm",
    "SendVerificationCodeForm",
)


class SendVerificationPurposeEnum(StrEnum):
    REGISTER = "register"
    RESET = "reset"


class OAuthLoginProviderEnum(StrEnum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"


class SendVerificationCodeForm(ApiFormModel):
    email: str = Body(..., embed=True, description="邮箱地址")
    purpose: SendVerificationPurposeEnum = Body(..., embed=True, description="用途：register 或 reset")


class RegisterForm(ApiFormModel):
    email: str = Body(..., embed=True, description="邮箱地址")
    password: str = Body(..., embed=True, description="密码")
    displayName: str = Body(..., embed=True, description="显示名称")
    otp: str = Body(..., embed=True, description="邮箱验证码")


class LoginForm(ApiFormModel):
    email: str = Body(..., embed=True, description="邮箱地址")
    password: str = Body(..., embed=True, description="密码")


class OAuthExchangeForm(ApiFormModel):
    provider: OAuthLoginProviderEnum = Body(..., embed=True, description="提供方：google / microsoft")
    code: str = Body(..., embed=True, description="OAuth 授权码")
    redirectUri: str = Body(..., embed=True, description="前端回调地址")
    codeVerifier: str = Body(..., embed=True, description="PKCE code_verifier")


class ForgotPasswordForm(ApiFormModel):
    email: str = Body(..., embed=True, description="邮箱地址")


class ResetPasswordForm(ApiFormModel):
    email: str = Body(..., embed=True, description="邮箱地址")
    otp: str = Body(..., embed=True, description="验证码")
    newPassword: str = Body(..., embed=True, description="新密码")


class ChangePasswordForm(ApiFormModel):
    oldPassword: str = Body(..., embed=True, description="当前密码")
    newPassword: str = Body(..., embed=True, description="新密码")


class RefreshTokenForm(ApiFormModel):
    refreshToken: str = Body(..., embed=True, description="刷新令牌")


class UpdateProfileForm(ApiFormModel):
    displayName: str = Body(..., embed=True, description="显示名称")
    avatarUrl: str | None = Body(None, embed=True, description="头像 OSS URL")
