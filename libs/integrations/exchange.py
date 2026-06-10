"""交易所 REST API 集成（账户信息：连接测试 / 余额 / 权限查询，非下单）。

真实调用，无拟真回退：用明文 api_key + api_secret 经 httpx 调交易所现货私有 REST
（Binance 风格：``GET /api/v3/account``，``timestamp`` 参数经 HMAC-SHA256 签名，
请求头带 ``X-MBX-APIKEY``）。权限位读 account 响应的 ``canTrade`` / ``canWithdraw`` /
``canDeposit``，余额读 ``balances`` 列表。

- 无可用明文凭证 → 抛 ``ExchangeCredentialsError``（提示重新录入，历史占位密文不可逆）。
- 请求失败（网络 / 签名被拒 / 限流）→ ``test_connection`` 返回 ``ok=False``（测试语义），
  其余函数抛 ``ExchangeRequestError``；message 面向用户展示。

REST base 经 ``EXCHANGE_API_BASE`` 覆盖（默认 https://api.binance.com）。其它交易所
（Bybit / OKX）签名口径不同，接入时在 ``_signed_account`` 内按 provider 分支。
函数保持同步签名（调用方在 async ``before()`` 内同步调用），内部用 ``httpx.Client``。
"""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from configs import get_settings
from libs.logger import logger

__all__ = (
    "ExchangeBalanceResult",
    "ExchangeConnectionResult",
    "ExchangeCredentialsError",
    "ExchangePermissionResult",
    "ExchangeRequestError",
    "fetch_balance",
    "fetch_permissions",
    "test_connection",
)

_ACCOUNT_PATH = "/api/v3/account"
_HTTP_TIMEOUT = 8.0
_RECV_WINDOW = 5000


class ExchangeCredentialsError(RuntimeError):
    """凭证缺失或不可用（含历史占位密文无法解密）；message 面向用户展示。"""


class ExchangeRequestError(RuntimeError):
    """交易所请求失败（网络 / 签名 / 限流）；message 面向用户展示。"""


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


def _exchange_base() -> str:
    return (getattr(get_settings(), "EXCHANGE_API_BASE", None) or "https://api.binance.com").rstrip("/")


def _require_credentials(api_key: str | None, api_secret: str | None) -> tuple[str, str]:
    key = (api_key or "").strip()
    secret = (api_secret or "").strip()
    if not key or not secret:
        raise ExchangeCredentialsError("交易所凭证不可用，请编辑账户重新录入 API Key 与 Secret")
    return key, secret


def _signed_account(api_key: str, api_secret: str) -> dict[str, object]:
    """调用 Binance ``GET /api/v3/account`` 并返回原始账户 JSON；异常向上抛。"""
    params = {"timestamp": int(time.time() * 1000), "recvWindow": _RECV_WINDOW}
    query = urllib.parse.urlencode(params)
    signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{_exchange_base()}{_ACCOUNT_PATH}?{query}&signature={signature}"
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.get(url, headers={"X-MBX-APIKEY": api_key})
        response.raise_for_status()
        return response.json()


def _quote_value_usdt(asset: str, free: float, locked: float) -> float:
    """把单一资产折合 USDT：稳定币 1:1，其余按数量近似（精确折算属行情服务职责）。"""
    return free + locked


def test_connection(exchange: str, api_key: str, api_secret: str) -> ExchangeConnectionResult:
    """连接测试：校验 API Key/Secret 可用性与权限安全性（可读 + 不可提现视为安全）。

    凭证缺失抛 ExchangeCredentialsError；请求失败返回 ok=False（测试本身的失败语义）。
    """
    key, secret = _require_credentials(api_key, api_secret)
    started = time.perf_counter()
    try:
        account = _signed_account(key, secret)
    except Exception as exc:
        logger.warning(f"exchange.test_connection 失败: {exc}")
        return ExchangeConnectionResult(
            ok=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
            message="连接失败，请检查 API Key/Secret 或网络可达性",
            permission_safe=False,
        )
    latency_ms = max(int((time.perf_counter() - started) * 1000), 1)
    can_withdraw = bool(account.get("canWithdraw", False))
    permission_safe = not can_withdraw
    message = "连接正常 · 权限已校验" if permission_safe else "连接正常 · 检测到提现权限"
    return ExchangeConnectionResult(ok=True, latency_ms=latency_ms, message=message, permission_safe=permission_safe)


def fetch_balance(exchange: str, api_key: str, api_secret: str) -> ExchangeBalanceResult:
    """同步账户余额（折合 USDT）。凭证缺失 / 请求失败抛异常，不回退。"""
    key, secret = _require_credentials(api_key, api_secret)
    try:
        account = _signed_account(key, secret)
    except Exception as exc:
        logger.warning(f"exchange.fetch_balance 失败: {exc}")
        raise ExchangeRequestError("余额同步失败，请稍后重试或检查 API Key 权限") from exc
    balances = account.get("balances", [])
    if not isinstance(balances, list):
        raise ExchangeRequestError("交易所返回数据异常，请稍后重试")
    breakdown: dict[str, float] = {}
    total = 0.0
    available = 0.0
    for row in balances:
        asset = str(row.get("asset", "")).upper()
        free = float(row.get("free", 0) or 0)
        locked = float(row.get("locked", 0) or 0)
        if free + locked <= 0:
            continue
        value = _quote_value_usdt(asset, free, locked)
        total += value
        available += _quote_value_usdt(asset, free, 0.0)
        breakdown[asset] = round(value, 8)
    return ExchangeBalanceResult(
        total_usdt=round(total, 2),
        available_usdt=round(available, 2),
        synced_at=datetime.now(UTC),
        breakdown=breakdown,
    )


def fetch_permissions(exchange: str, api_key: str, api_secret: str) -> ExchangePermissionResult:
    """查询 API Key 权限明细。凭证缺失 / 请求失败抛异常，不回退。

    IP 白名单需管理类端点（``GET /sapi/v1/account/apiRestrictions``）才可读，账户端点
    不含，故白名单字段以保守默认呈现。
    """
    key, secret = _require_credentials(api_key, api_secret)
    try:
        account = _signed_account(key, secret)
    except Exception as exc:
        logger.warning(f"exchange.fetch_permissions 失败: {exc}")
        raise ExchangeRequestError("权限查询失败，请稍后重试或检查 API Key") from exc
    return ExchangePermissionResult(
        can_read=bool(account.get("canDeposit", True)),
        can_trade=bool(account.get("canTrade", False)),
        can_withdraw=bool(account.get("canWithdraw", False)),
        ip_whitelisted=False,
        ip_whitelist=[],
    )
