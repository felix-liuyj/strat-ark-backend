"""交易所 REST API 集成 stub。

返回拟真 mock 数据；函数签名按真实交易所（Binance / Bybit / OKX）集成预留：
真实实现时这里会用商户 API Key/Secret 调用对应交易所的 REST 端点（连接测试、余额、
权限查询等）。当前阶段不发起任何真实网络请求、不接触真实资金。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

__all__ = (
    "ExchangeBalanceResult",
    "ExchangeConnectionResult",
    "ExchangePermissionResult",
    "fetch_balance",
    "fetch_permissions",
    "test_connection",
)


@dataclass(slots=True)
class ExchangeConnectionResult:
    """连接测试结果。"""

    ok: bool
    latency_ms: int
    message: str
    permission_safe: bool


@dataclass(slots=True)
class ExchangeBalanceResult:
    """余额同步结果（折合 USDT）。"""

    total_usdt: float
    available_usdt: float
    synced_at: datetime
    breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ExchangePermissionResult:
    """API Key 权限明细。"""

    can_read: bool
    can_trade: bool
    can_withdraw: bool
    ip_whitelisted: bool
    ip_whitelist: list[str] = field(default_factory=list)


def test_connection(exchange: str, api_key: str, api_secret: str) -> ExchangeConnectionResult:
    """连接测试：校验 API Key/Secret 可用性与权限安全性（mock）。

    真实实现：用凭证请求交易所账户信息端点，根据 HTTP 状态与返回权限位判断。
    """
    return ExchangeConnectionResult(
        ok=True,
        latency_ms=42,
        message="连接正常 · 权限已校验",
        permission_safe=True,
    )


def fetch_balance(exchange: str, api_key: str, api_secret: str) -> ExchangeBalanceResult:
    """同步账户余额（mock，折合 USDT）。

    真实实现：调用交易所余额端点并按行情折算为 USDT 计价。
    """
    presets: dict[str, float] = {"binance": 12520.0, "bybit": 7620.0}
    total = presets.get(exchange.lower(), 5000.0)
    return ExchangeBalanceResult(
        total_usdt=total,
        available_usdt=round(total * 0.82, 2),
        synced_at=datetime.now(UTC),
        breakdown={"USDT": round(total * 0.6, 2), "BTC": round(total * 0.3, 2), "ETH": round(total * 0.1, 2)},
    )


def fetch_permissions(exchange: str, api_key: str, api_secret: str) -> ExchangePermissionResult:
    """查询 API Key 权限明细（mock）。

    真实实现：读取交易所 API Key 权限配置，映射读取/交易/提现/IP 白名单等位。
    """
    return ExchangePermissionResult(
        can_read=True,
        can_trade=True,
        can_withdraw=False,
        ip_whitelisted=True,
        ip_whitelist=["10.0.0.0/24"],
    )
