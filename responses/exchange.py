"""交易所账户响应模型（camelCase）。

字段形状对齐前端 ExchangeAccountsPage：账户卡（名称 / 权限 / 余额 / 安全检查项 /
最近同步）、连接测试结果、权限详情。
"""

from pydantic import Field

from libs.schema import ApiResponseModel
from models.exchange import ExchangePermissionEnum, ExchangeProviderEnum, ExchangeStatusEnum

__all__ = (
    "ExchangeAccountResponseData",
    "ExchangeBalanceResponseData",
    "ExchangeConnectionTestResponseData",
    "ExchangePermissionResponseData",
    "ExchangeSecurityCheckResponseData",
)


class ExchangeSecurityCheckResponseData(ApiResponseModel):
    """单个安全检查项（前端绿勾 ok / 琥珀告警 warn）。"""

    key: str = Field(..., description="检查项标识：withdraw / ipWhitelist / tradeOnly")
    label: str = Field(..., description="展示文案")
    passed: bool = Field(..., description="是否通过（true 绿勾，false 琥珀告警）")


class ExchangeAccountResponseData(ApiResponseModel):
    id: int = Field(..., description="交易所账户 ID")
    name: str = Field(..., description="账户名称")
    provider: ExchangeProviderEnum = Field(..., description="交易所")
    status: ExchangeStatusEnum = Field(..., description="连接状态")
    permission: ExchangePermissionEnum = Field(..., description="授权范围")
    permissionLabel: str = Field(..., description="权限展示文案，例如 读取 / 交易")
    apiKeyMask: str = Field(..., description="API Key 掩码，例如 ····7f3a（不明文回显）")
    ipWhitelist: str = Field(..., description="IP 白名单")
    isDefault: bool = Field(..., description="是否默认交易所")
    balanceUsdt: float = Field(..., description="余额（折合 USDT）")
    balanceLabel: str = Field(..., description="余额展示文案，例如 12,520 USDT")
    lastSyncedAt: str | None = Field(None, description="最近同步时间")
    checks: list[ExchangeSecurityCheckResponseData] = Field(..., description="安全检查项列表")


class ExchangeConnectionTestResponseData(ApiResponseModel):
    ok: bool = Field(..., description="连接是否正常")
    latencyMs: int = Field(..., description="握手延迟（毫秒）")
    message: str = Field(..., description="结果文案")
    permissionSafe: bool = Field(..., description="权限是否安全（未开启提现等）")


class ExchangeBalanceResponseData(ApiResponseModel):
    balanceUsdt: float = Field(..., description="总余额（折合 USDT）")
    availableUsdt: float = Field(..., description="可用余额（折合 USDT）")
    syncedAt: str = Field(..., description="同步时间")
    breakdown: dict[str, float] = Field(..., description="各币种余额明细")


class ExchangePermissionResponseData(ApiResponseModel):
    canRead: bool = Field(..., description="读取余额权限")
    canTrade: bool = Field(..., description="现货 / 合约交易权限")
    canWithdraw: bool = Field(..., description="提现权限（应禁用）")
    ipWhitelisted: bool = Field(..., description="是否启用 IP 白名单")
    ipWhitelist: list[str] = Field(..., description="IP 白名单列表")
