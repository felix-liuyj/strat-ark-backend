"""Freqtrade 编排与实例运行时集成（真实 REST，无 mock）。

两层客户端：
- **编排器**（orchestrator，engines/freqtrade-orchestrator）：per-bot 实例容器的
  生命周期（创建 / 启停 / 重启 / 销毁 / 状态），Bearer token 鉴权；配置来自引擎
  管理页 freqtrade ``connection_config``（orchestratorUrl / orchestratorToken /
  instanceImage），经 ``resolve_orchestrator_config`` 合成。
- **实例 REST**：freqtrade 原生 api_server（``POST /api/v1/token/login`` Basic 换
  JWT），拉取交易 / 持仓 / 日志 / 当日收益；实例凭证由 bot 启动时随机生成、
  加密存于 Bot 行。

无回退：编排器未配置或任何调用失败抛 ``FreqtradeUnavailableError``（message 面向
用户展示），由 ViewModel 转为业务错误。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from libs.logger import logger

__all__ = (
    "FreqtradeUnavailableError",
    "InstanceCredentials",
    "InstanceInfo",
    "LogEntry",
    "OrchestratorConfig",
    "PositionSnapshot",
    "TradeRecord",
    "create_instance",
    "fetch_daily_profit_pct",
    "fetch_logs",
    "fetch_positions",
    "fetch_trades",
    "get_instance",
    "remove_instance",
    "resolve_orchestrator_config",
    "restart_instance",
    "stop_instance",
)

_HTTP_TIMEOUT = 15.0

_ORCHESTRATOR_NOT_CONFIGURED = "Freqtrade 编排器未配置，请管理员在引擎管理页填写编排器地址与令牌"
_ORCHESTRATOR_CALL_FAILED = "Freqtrade 编排器调用失败，请检查编排服务是否在线"
_INSTANCE_CALL_FAILED = "Bot 实例接口调用失败，实例可能未运行或正在启动"


class FreqtradeUnavailableError(RuntimeError):
    """编排器 / 实例不可用（未配置或调用失败）；message 直接面向用户展示。"""


@dataclass(slots=True)
class OrchestratorConfig:
    """编排器控制面配置快照（引擎管理页落库）。"""

    url: str | None
    token: str | None
    instance_image: str
    timeout: float

    @property
    def ready(self) -> bool:
        return bool(self.url and self.token)


def resolve_orchestrator_config(connection_config: dict[str, Any] | None) -> OrchestratorConfig:
    """从引擎管理页落库的 freqtrade connection_config 合成编排器配置（单一事实源）。"""
    cc = connection_config or {}
    return OrchestratorConfig(
        url=str(cc.get("orchestratorUrl") or "").strip().rstrip("/") or None,
        token=str(cc.get("orchestratorToken") or "").strip() or None,
        instance_image=str(cc.get("instanceImage") or "").strip(),
        timeout=float(cc.get("timeout") or 30),
    )


@dataclass(slots=True)
class InstanceCredentials:
    """单个 bot 实例的 REST 访问信息（api_server 凭证随实例生成）。"""

    api_url: str
    username: str
    password: str


@dataclass(slots=True)
class InstanceInfo:
    """实例容器状态（编排器视角）。"""

    ref: str
    status: str
    health: str
    started_at: str | None = None


@dataclass(slots=True)
class TradeRecord:
    """单笔已平仓交易。"""

    pair: str
    side: str
    open_price: float
    close_price: float
    amount: float
    pnl_amount: float
    pnl_pct: float
    opened_at: datetime
    closed_at: datetime
    duration: str


@dataclass(slots=True)
class PositionSnapshot:
    """单个未平仓持仓。"""

    pair: str
    side: str
    open_price: float
    current_price: float
    amount: float
    value_usdt: float
    unrealized_pnl_amount: float
    unrealized_pnl_pct: float
    stop_loss_price: float


@dataclass(slots=True)
class LogEntry:
    """单条实例日志。"""

    timestamp: datetime
    level: str
    message: str
    metadata: dict[str, str] = field(default_factory=dict)


# ============================ 编排器客户端 ============================


def _require_orchestrator(cfg: OrchestratorConfig) -> tuple[str, dict[str, str]]:
    if not cfg.ready:
        raise FreqtradeUnavailableError(_ORCHESTRATOR_NOT_CONFIGURED)
    return str(cfg.url), {"Authorization": f"Bearer {cfg.token}"}


async def _orchestrator_request(
    cfg: OrchestratorConfig, method: str, path: str, json_body: dict | None = None
) -> Any:
    base, headers = _require_orchestrator(cfg)
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout or _HTTP_TIMEOUT) as client:
            response = await client.request(method, f"{base}{path}", headers=headers, json=json_body)
            response.raise_for_status()
            return response.json()
    except FreqtradeUnavailableError:
        raise
    except Exception as exc:
        logger.warning(f"freqtrade orchestrator {method} {path} 失败: {exc}")
        raise FreqtradeUnavailableError(_ORCHESTRATOR_CALL_FAILED) from exc


def _instance_from_payload(payload: dict) -> InstanceInfo:
    return InstanceInfo(
        ref=str(payload.get("ref", "")),
        status=str(payload.get("status", "unknown")),
        health=str(payload.get("health", "none")),
        started_at=payload.get("startedAt"),
    )


async def create_instance(
    cfg: OrchestratorConfig, *, ref: str, strategy: str, env: dict[str, str]
) -> InstanceInfo:
    """创建并启动 bot 实例容器（同名实例先销毁重建，携带最新配置与凭证）。"""
    payload = await _orchestrator_request(
        cfg,
        "POST",
        "/instances",
        {"ref": ref, "strategy": strategy, "image": cfg.instance_image, "env": env},
    )
    return _instance_from_payload(payload)


async def stop_instance(cfg: OrchestratorConfig, ref: str) -> InstanceInfo:
    return _instance_from_payload(await _orchestrator_request(cfg, "POST", f"/instances/{ref}/stop"))


async def restart_instance(cfg: OrchestratorConfig, ref: str) -> InstanceInfo:
    return _instance_from_payload(await _orchestrator_request(cfg, "POST", f"/instances/{ref}/restart"))


async def remove_instance(cfg: OrchestratorConfig, ref: str) -> None:
    await _orchestrator_request(cfg, "DELETE", f"/instances/{ref}")


async def get_instance(cfg: OrchestratorConfig, ref: str) -> InstanceInfo | None:
    """查询实例状态；实例不存在返回 None（其余失败仍抛错）。"""
    base, headers = _require_orchestrator(cfg)
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout or _HTTP_TIMEOUT) as client:
            response = await client.get(f"{base}/instances/{ref}", headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return _instance_from_payload(response.json())
    except Exception as exc:
        logger.warning(f"freqtrade orchestrator get_instance({ref}) 失败: {exc}")
        raise FreqtradeUnavailableError(_ORCHESTRATOR_CALL_FAILED) from exc


# ============================ 实例 REST 客户端 ============================


async def _instance_get(creds: InstanceCredentials, path: str, params: dict | None = None) -> Any:
    """带 JWT 的实例 REST GET：先 Basic 登录换 access_token，再请求目标端点。"""
    base = creds.api_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            login = await client.post(
                f"{base}/api/v1/token/login", auth=(creds.username, creds.password)
            )
            login.raise_for_status()
            token = str(login.json().get("access_token", ""))
            response = await client.get(
                f"{base}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.warning(f"freqtrade instance GET {path} 失败: {exc}")
        raise FreqtradeUnavailableError(_INSTANCE_CALL_FAILED) from exc


def _parse_dt(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _format_duration(opened_at: datetime, closed_at: datetime) -> str:
    total_minutes = max(int((closed_at - opened_at).total_seconds() // 60), 0)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


async def fetch_trades(creds: InstanceCredentials, limit: int = 50) -> list[TradeRecord]:
    """已平仓交易（GET /api/v1/trades）。"""
    payload = await _instance_get(creds, "/api/v1/trades", {"limit": limit})
    records: list[TradeRecord] = []
    for row in payload.get("trades", []):
        opened_at = _parse_dt(row.get("open_date"))
        closed_at = _parse_dt(row.get("close_date"))
        records.append(
            TradeRecord(
                pair=str(row.get("pair", "")),
                side="short" if row.get("is_short") else "long",
                open_price=float(row.get("open_rate", 0) or 0),
                close_price=float(row.get("close_rate", 0) or 0),
                amount=float(row.get("amount", 0) or 0),
                pnl_amount=round(float(row.get("close_profit_abs", 0) or 0), 2),
                pnl_pct=round(float(row.get("close_profit", 0) or 0) * 100, 2),
                opened_at=opened_at,
                closed_at=closed_at,
                duration=_format_duration(opened_at, closed_at),
            )
        )
    return records


async def fetch_positions(creds: InstanceCredentials) -> list[PositionSnapshot]:
    """未平仓持仓（GET /api/v1/status）。"""
    payload = await _instance_get(creds, "/api/v1/status")
    positions: list[PositionSnapshot] = []
    for row in payload if isinstance(payload, list) else []:
        open_rate = float(row.get("open_rate", 0) or 0)
        current_rate = float(row.get("current_rate", 0) or 0)
        amount = float(row.get("amount", 0) or 0)
        positions.append(
            PositionSnapshot(
                pair=str(row.get("pair", "")),
                side="short" if row.get("is_short") else "long",
                open_price=open_rate,
                current_price=current_rate,
                amount=amount,
                value_usdt=round(float(row.get("stake_amount", 0) or 0), 2),
                unrealized_pnl_amount=round(float(row.get("profit_abs", 0) or 0), 2),
                unrealized_pnl_pct=round(float(row.get("profit_ratio", 0) or 0) * 100, 2),
                stop_loss_price=float(row.get("stop_loss_abs", 0) or 0),
            )
        )
    return positions


async def fetch_logs(
    creds: InstanceCredentials, level: str | None = None, limit: int = 100
) -> list[LogEntry]:
    """实例日志（GET /api/v1/logs；freqtrade 行格式 [date, ts, name, level, message]）。"""
    payload = await _instance_get(creds, "/api/v1/logs", {"limit": limit})
    entries: list[LogEntry] = []
    for row in payload.get("logs", []):
        if not isinstance(row, list) or len(row) < 5:
            continue
        entries.append(
            LogEntry(
                timestamp=_parse_dt(row[0]),
                level=str(row[3]).upper(),
                message=str(row[4]),
            )
        )
    if level and level.upper() != "ALL":
        wanted = level.upper()
        entries = [entry for entry in entries if entry.level == wanted]
    return entries[:limit]


async def fetch_daily_profit_pct(creds: InstanceCredentials) -> float:
    """当日收益百分比（GET /api/v1/daily?timescale=1），守护轮询的日亏检查用。"""
    payload = await _instance_get(creds, "/api/v1/daily", {"timescale": 1})
    rows = payload.get("data", [])
    if not rows:
        return 0.0
    raw = rows[0].get("rel_profit", 0)
    return round(float(raw or 0) * 100, 4)
