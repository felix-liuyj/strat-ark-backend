"""交易所账户请求表单（camelCase Body）。"""

from fastapi import Body

from libs.schema import ApiFormModel
from models.exchange import ExchangeProviderEnum

__all__ = (
    "ExchangeAccountCreateForm",
    "ExchangeAccountUpdateForm",
)


class ExchangeAccountCreateForm(ApiFormModel):
    name: str = Body(..., embed=True, description="账户名称，例如 主账户")
    provider: ExchangeProviderEnum = Body(..., embed=True, description="交易所：binance / bybit / okx")
    apiKey: str = Body(..., embed=True, description="API Key（加密存储，不明文回显）")
    apiSecret: str = Body(..., embed=True, description="API Secret（加密存储，不明文回显）")
    ipWhitelist: str | None = Body(None, embed=True, description="IP 白名单（可选），例如 10.0.0.0/24")


class ExchangeAccountUpdateForm(ApiFormModel):
    name: str | None = Body(None, embed=True, description="账户名称")
    apiKey: str | None = Body(None, embed=True, description="新 API Key（留空则不更新）")
    apiSecret: str | None = Body(None, embed=True, description="新 API Secret（留空则不更新）")
    ipWhitelist: str | None = Body(None, embed=True, description="IP 白名单")
