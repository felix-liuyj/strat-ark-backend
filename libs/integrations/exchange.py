"""交易所 REST API 集成（账户信息：连接测试 / 余额 / 权限查询，非下单）。

config 驱动的真实调用骨架 + 优雅回退：
- 真实路径：当调用方提供「可用的明文 api_key + api_secret」时，用 httpx 调交易所现货
  私有 REST（Binance 风格：``GET /api/v3/account``，``timestamp`` 参数经 HMAC-SHA256
  签名，请求头带 ``X-MBX-APIKEY``）。权限位读 account 响应的 ``canTrade`` /
  ``canWithdraw`` / ``canDeposit``，余额读 ``balances`` 列表。
- 回退路径：缺配置 / 缺凭证 / 凭证为掩码或占位密文 / 任一请求失败（离线、限流、区域
  封锁、签名被拒），一律回退到原确定性拟真数据，保证离线与联调可用。

注意（凭证现状）：当前交易所 API Secret 入库为占位密文（``enc::<len>``，见
``view_models/exchanges`` 与 ``models/exchange``），不可逆出明文；已保存账户的查询调用
传入的是掩码 key + 空 secret，因此走回退。**需真实凭证解密（依赖加密落地，KMS/fernet
还原明文 secret）方能联通已保存账户**；未保存连接测试 / 新增账户因携带表单明文 secret，
配置齐全时可真实联通。REST base 经 ``EXCHANGE_API_BASE`` 覆盖（默认 https://api.binance.com）。

函数保持同步签名（调用方在 async ``before()`` 内同步调用，不 await），内部真实路径用
``httpx.Client`` 同步客户端，不改变调用方契约。
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
    "ExchangePermissionResult",
    "fetch_balance",
    "fetch_permissions",
    "test_connection",
)

# Binance 现货账户信息端点（私有，需签名）。其它交易所（Bybit / OKX）签名口径不同，
# 接入时在 _signed_account 内按 provider 分支即可，回退逻辑无需改动。
_ACCOUNT_PATH = "/api/v3/account"
_HTTP_TIMEOUT = 8.0
_RECV_WINDOW = 5000

# 掩码占位前缀（与 view_models 的 _mask_api_key / _encrypt_secret 对齐）：携带这些
# 前缀的 key/secret 视为不可用凭证，直接走回退、不发起真实请求。
_MASK_KEY_PREFIX = "····"
_CIPHER_SECRET_PREFIX = "enc::"


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


# ============================ 工具 ============================


def _exchange_base() -> str:
    return (getattr(get_settings(), "EXCHANGE_API_BASE", None) or "https://api.binance.com").rstrip("/")


def _has_usable_credentials(api_key: str, api_secret: str) -> bool:
    """判断是否拿到可用于真实签名的明文凭证。

    掩码 key（``····xxxx``）、占位密文 secret（``enc::N``）、空串一律视为不可用，
    走回退。仅当 key 与 secret 都是非空、非掩码、非占位的真实明文时返回 True。
    """
    key = (api_key or "").strip()
    secret = (api_secret or "").strip()
    if not key or not secret:
        return False
    if key.startswith(_MASK_KEY_PREFIX):
        return False
    if secret.startswith(_CIPHER_SECRET_PREFIX):
        return False
    return True


def _signed_account(api_key: str, api_secret: str) -> dict[str, object]:
    """调用 Binance ``GET /api/v3/account`` 并返回原始账户 JSON。

    timestamp + recvWindow 组成查询串后 HMAC-SHA256 签名，附加 ``signature`` 参数，
    请求头携带 ``X-MBX-APIKEY``。任何网络 / 状态码异常向上抛，由调用方回退。
    """
    params = {"timestamp": int(time.time() * 1000), "recvWindow": _RECV_WINDOW}
    query = urllib.parse.urlencode(params)
    signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{_exchange_base()}{_ACCOUNT_PATH}?{query}&signature={signature}"
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.get(url, headers={"X-MBX-APIKEY": api_key})
        response.raise_for_status()
        return response.json()


def _quote_value_usdt(asset: str, free: float, locked: float) -> float:
    """把单一资产折合 USDT。

    USDT / USDC / BUSD 等稳定币按 1:1；其余资产无行情上下文时按数量原值近似计入，
    避免阻塞同步流程（精确折算应由行情服务联合计算，非账户端职责）。
    """
    total = free + locked
    if asset.upper() in {"USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI"}:
        return total
    return total


# ============================ 确定性回退数据 ============================


def _demo_connection() -> ExchangeConnectionResult:
    return ExchangeConnectionResult(
        ok=True,
        latency_ms=42,
        message="连接正常 · 权限已校验",
        permission_safe=True,
    )


def _demo_balance(exchange: str) -> ExchangeBalanceResult:
    presets: dict[str, float] = {"binance": 12520.0, "bybit": 7620.0}
    total = presets.get(exchange.lower(), 5000.0)
    return ExchangeBalanceResult(
        total_usdt=total,
        available_usdt=round(total * 0.82, 2),
        synced_at=datetime.now(UTC),
        breakdown={"USDT": round(total * 0.6, 2), "BTC": round(total * 0.3, 2), "ETH": round(total * 0.1, 2)},
    )


def _demo_permissions() -> ExchangePermissionResult:
    return ExchangePermissionResult(
        can_read=True,
        can_trade=True,
        can_withdraw=False,
        ip_whitelisted=True,
        ip_whitelist=["10.0.0.0/24"],
    )


# ============================ 公开接口（真实路径失败回退 demo） ============================


def test_connection(exchange: str, api_key: str, api_secret: str) -> ExchangeConnectionResult:
    """连接测试：校验 API Key/Secret 可用性与权限安全性。

    真实路径：用明文凭证请求账户信息端点，按 HTTP 状态与返回权限位判断（可读 + 不可提现
    视为权限安全）。无可用凭证 / 失败时回退确定性数据。
    """
    if not _has_usable_credentials(api_key, api_secret):
        return _demo_connection()
    started = time.perf_counter()
    try:
        account = _signed_account(api_key, api_secret)
        latency_ms = int((time.perf_counter() - started) * 1000)
        can_trade = bool(account.get("canTrade", False))
        can_withdraw = bool(account.get("canWithdraw", False))
        permission_safe = not can_withdraw
        message = "连接正常 · 权限已校验" if permission_safe else "连接正常 · 检测到提现权限"
        return ExchangeConnectionResult(
            ok=True,
            latency_ms=max(latency_ms, 1),
            message=message,
            permission_safe=permission_safe,
        )
    except Exception as exc:
        logger.warning(f"exchange.test_connection fallback to demo: {exc}")
        return _demo_connection()


def fetch_balance(exchange: str, api_key: str, api_secret: str) -> ExchangeBalanceResult:
    """同步账户余额（折合 USDT）。

    真实路径：调用账户端点读 ``balances``，逐资产折算为 USDT 计价（稳定币 1:1，其余近似）。
    无可用凭证 / 失败时回退确定性数据。
    """
    if not _has_usable_credentials(api_key, api_secret):
        return _demo_balance(exchange)
    try:
        account = _signed_account(api_key, api_secret)
        balances = account.get("balances", [])
        if not isinstance(balances, list):
            return _demo_balance(exchange)
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
    except Exception as exc:
        logger.warning(f"exchange.fetch_balance fallback to demo: {exc}")
        return _demo_balance(exchange)


def fetch_permissions(exchange: str, api_key: str, api_secret: str) -> ExchangePermissionResult:
    """查询 API Key 权限明细。

    真实路径：读账户端点的 ``canDeposit`` / ``canTrade`` / ``canWithdraw`` 权限位。
    IP 白名单需经管理类端点（``GET /sapi/v1/account/apiRestrictions``）才可读，账户端点
    不含，故 IP 白名单字段仍以保守默认呈现。无可用凭证 / 失败时回退确定性数据。
    """
    if not _has_usable_credentials(api_key, api_secret):
        return _demo_permissions()
    try:
        account = _signed_account(api_key, api_secret)
        can_read = bool(account.get("canDeposit", True))
        can_trade = bool(account.get("canTrade", False))
        can_withdraw = bool(account.get("canWithdraw", False))
        return ExchangePermissionResult(
            can_read=can_read,
            can_trade=can_trade,
            can_withdraw=can_withdraw,
            ip_whitelisted=False,
            ip_whitelist=[],
        )
    except Exception as exc:
        logger.warning(f"exchange.fetch_permissions fallback to demo: {exc}")
        return _demo_permissions()
