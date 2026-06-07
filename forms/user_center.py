"""用户中心域请求表单。"""

from fastapi import Body

from libs.schema import ApiFormModel
from models.user_center import ApiKeyPermissionEnum, OAuthProviderEnum

__all__ = (
    "BindOAuthForm",
    "CreateApiKeyForm",
    "UpdateTwoFactorForm",
)


class CreateApiKeyForm(ApiFormModel):
    """创建平台 API Key。

    expiryDays 为 None 表示永不过期；明文密钥仅在创建响应中返回一次。
    """

    name: str = Body(..., embed=True, description="密钥名称")
    permission: ApiKeyPermissionEnum = Body(
        ApiKeyPermissionEnum.READ, embed=True, description="权限：read 只读 / read_write 读写"
    )
    expiryDays: int | None = Body(None, embed=True, description="有效天数；不传表示永不过期")


class BindOAuthForm(ApiFormModel):
    """绑定第三方账号（模拟，不发起真实 OAuth 授权）。

    accountLabel 为该第三方账号的展示标识（邮箱 / 用户名）。
    """

    provider: OAuthProviderEnum = Body(..., embed=True, description="提供方：google / microsoft / github / apple")
    accountLabel: str = Body("", embed=True, description="第三方账号展示标识")


class UpdateTwoFactorForm(ApiFormModel):
    """更新两步验证（2FA）开关。"""

    totpEnabled: bool = Body(..., embed=True, description="身份验证器 App (TOTP) 是否开启")
    requireForLiveActions: bool = Body(
        True, embed=True, description="实盘操作是否要求 2FA"
    )
