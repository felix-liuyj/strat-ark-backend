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
    """绑定第三方账号。

    当前绑定必须经真实 OAuth 授权码回调完成；直接提交 provider 不会落库绑定。
    """

    provider: OAuthProviderEnum = Body(..., embed=True, description="提供方：google / microsoft / github / apple")
    accountLabel: str = Body("", embed=True, description="第三方账号展示标识")


class UpdateTwoFactorForm(ApiFormModel):
    """更新两步验证（2FA）。

    开启 / 关闭 TOTP 必须携带 totpCode（用当前绑定的 secret 校验通过才生效，先经
    /user/two-factor/setup 获取绑定二维码）；仅调整 requireForLiveActions 时 totpCode 可省略。
    """

    totpEnabled: bool = Body(..., embed=True, description="身份验证器 App (TOTP) 是否开启")
    requireForLiveActions: bool = Body(True, embed=True, description="实盘操作是否要求 2FA")
    totpCode: str | None = Body(None, embed=True, description="6 位 TOTP 验证码（开启 / 关闭时必填）")
