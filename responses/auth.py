"""Authentication response data models."""

from pydantic import Field

from libs.schema import ApiResponseModel
from models.account import PlanEnum, UserTypeEnum

__all__ = (
    "AuthTokenResponseData",
    "UserProfileResponseData",
)


class UserProfileResponseData(ApiResponseModel):
    id: int = Field(..., description="用户 ID")
    email: str = Field(..., description="邮箱")
    displayName: str = Field(..., description="显示名称")
    userType: UserTypeEnum = Field(..., description="用户类型")
    plan: PlanEnum = Field(..., description="订阅套餐")
    isAdmin: bool = Field(..., description="是否管理员")
    isVerified: bool = Field(..., description="是否已验证邮箱")
    avatarUrl: str | None = Field(None, description="头像 URL")


class AuthTokenResponseData(ApiResponseModel):
    accessToken: str = Field(..., description="访问令牌")
    refreshToken: str = Field(..., description="刷新令牌")
    user: UserProfileResponseData = Field(..., description="用户信息")
