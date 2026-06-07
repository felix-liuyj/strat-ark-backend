"""用户中心域响应数据模型。

覆盖前端 UserCenterPage：API Key 列表 / 创建（含明文一次）、OAuth 绑定、会话、2FA。
"""

from pydantic import Field

from libs.schema import ApiResponseModel
from models.user_center import ApiKeyPermissionEnum, OAuthProviderEnum

__all__ = (
    "ApiKeyCreatedResponseData",
    "ApiKeyResponseData",
    "OAuthBindingResponseData",
    "TwoFactorResponseData",
    "UserSessionResponseData",
)


class ApiKeyResponseData(ApiResponseModel):
    """API Key 列表项（不含明文，仅掩码展示）。"""

    id: int = Field(..., description="密钥 ID")
    name: str = Field(..., description="密钥名称")
    keyPrefix: str = Field(..., description="掩码展示串，如 sk_live_····a91f")
    permission: ApiKeyPermissionEnum = Field(..., description="权限")
    active: bool = Field(..., description="是否活跃（未撤销且未过期）")
    revoked: bool = Field(..., description="是否已撤销")
    lastUsedAt: str | None = Field(None, description="最近使用时间")
    expiresAt: str | None = Field(None, description="过期时间")


class ApiKeyCreatedResponseData(ApiResponseModel):
    """创建 API Key 结果：明文密钥仅此一次返回。"""

    id: int = Field(..., description="密钥 ID")
    name: str = Field(..., description="密钥名称")
    permission: ApiKeyPermissionEnum = Field(..., description="权限")
    # 明文密钥，仅创建时返回一次，请前端立即提示用户保存。
    plaintextKey: str = Field(..., description="明文密钥（仅本次返回）")
    keyPrefix: str = Field(..., description="掩码展示串")
    expiresAt: str | None = Field(None, description="过期时间")


class OAuthBindingResponseData(ApiResponseModel):
    """第三方账号绑定项（与前端 OAuthProvider 对齐）。"""

    provider: OAuthProviderEnum = Field(..., description="提供方")
    bound: bool = Field(..., description="是否已绑定")
    accountLabel: str | None = Field(None, description="第三方账号展示标识")
    linkedAt: str | None = Field(None, description="绑定时间")


class UserSessionResponseData(ApiResponseModel):
    """活跃会话项（与前端 SessionItem 对齐）。"""

    id: int = Field(..., description="会话 ID")
    device: str = Field(..., description="设备描述")
    deviceKind: str = Field(..., description="设备类型：desktop / mobile")
    location: str = Field(..., description="登录地点")
    current: bool = Field(..., description="是否当前设备")
    active: bool = Field(..., description="是否活跃")
    lastActiveAt: str | None = Field(None, description="最近活跃时间")


class TwoFactorResponseData(ApiResponseModel):
    """两步验证（2FA）状态。"""

    totpEnabled: bool = Field(..., description="TOTP 是否开启")
    requireForLiveActions: bool = Field(..., description="实盘操作是否要求 2FA")
