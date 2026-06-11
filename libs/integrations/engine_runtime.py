"""引擎运行时集成（freqtrade / tradingagents 经服务连接交互）。

部署模型：两个引擎**不做 K8s 集群化**，作为独立服务运行，backend 通过它们**暴露的
HTTP API**（``connection_config.serviceUrl``）做服务连接交互。监控为纯服务连接视图，不含
容器组 / 副本 / 主机资源等编排级概念。

- 连接 / 运行状态：``test_connection`` 与 ``fetch_runtime_snapshot`` 用 httpx 探测引擎
  serviceUrl（任意 HTTP 响应即视为在线并计时）；未配置 serviceUrl 或不可达时如实反映。
- 运营指标 / 依赖 / 日志：仅返回引擎真实暴露的数据；当前未约定端点时返回空集合。
- 运维操作（reload / stop 等）映射到引擎暴露的控制 API；缺少端点时返回失败。

函数保持同步签名（调用方在 async ``before()`` 内同步调用），内部用 ``httpx.Client``。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from libs.logger import logger

__all__ = (
    "DependencyHealth",
    "EngineLogEntry",
    "EngineOpResult",
    "EngineRuntimeSnapshot",
    "clear_queue_engine",
    "drain_engine",
    "emergency_stop_engine",
    "fetch_dependencies",
    "fetch_logs",
    "fetch_runtime_snapshot",
    "reload_engine",
    "tear_down_engine",
    "test_connection",
    "trigger_restart",
)

_HTTP_TIMEOUT = 6.0


@dataclass(slots=True)
class DependencyHealth:
    """单个外部依赖的健康度。"""

    name: str
    kind: str
    status: str
    latency: str | None = None


@dataclass(slots=True)
class EngineLogEntry:
    """单条引擎日志。"""

    timestamp: datetime
    level: str
    message: str


@dataclass(slots=True)
class EngineRuntimeSnapshot:
    """引擎运行时聚合快照（服务连接视图）。"""

    runtime_status: str
    connected: bool
    service_url: str
    latency_ms: float | None
    queue_depth: int
    error_rate: str
    synced_at: datetime
    metrics: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class EngineOpResult:
    """引擎运维操作结果（restart / reload / stop 等）。"""

    ok: bool
    engine_key: str
    operation: str
    runtime_status: str
    message: str
    executed_at: datetime


def _probe_service(service_url: str) -> tuple[bool, float | None]:
    """探测引擎暴露的 HTTP 服务是否可达（任意 HTTP 响应即视为在线），返回 (可达, 毫秒延迟)。"""
    url = service_url.strip()
    if not url:
        return False, None
    try:
        started = time.monotonic()
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            client.get(url)
        return True, round((time.monotonic() - started) * 1000, 1)
    except Exception as exc:
        logger.warning(f"engine_runtime probe failed for {url}: {exc}")
        return False, None


def _control_url(service_url: str, path: str) -> str:
    base = service_url.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{base}{suffix}"


def _headers(token: str = "") -> dict[str, str]:
    headers = {"content-type": "application/json"}
    if token.strip():
        headers["authorization"] = f"Bearer {token.strip()}"
    return headers


def _post_control(
    engine_key: str,
    operation: str,
    service_url: str,
    *,
    token: str = "",
    path: str = "",
) -> EngineOpResult:
    if not service_url.strip():
        return _build_op_result(engine_key, operation, "unknown", "未配置服务地址", ok=False)
    if not path.strip():
        return _build_op_result(engine_key, operation, "unknown", "未配置该操作的控制端点", ok=False)
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.post(_control_url(service_url, path), headers=_headers(token))
        if response.is_success:
            return _build_op_result(engine_key, operation, "running", "控制指令已下发", ok=True)
        message = f"控制端点返回 HTTP {response.status_code}"
        return _build_op_result(engine_key, operation, "degraded", message, ok=False)
    except Exception as exc:
        logger.warning(f"engine_runtime control failed for {engine_key}/{operation}: {exc}")
        return _build_op_result(engine_key, operation, "degraded", f"控制端点不可达：{exc}", ok=False)


# ============================ 监控读取（连接 / 状态经 serviceUrl 探活） ============================


def fetch_runtime_snapshot(engine_key: str, service_url: str = "") -> EngineRuntimeSnapshot:
    """读取引擎运行时聚合快照（服务连接视图）。

    经 serviceUrl 探活派生连接状态与延迟：可达 -> connected + running；不可达 -> degraded；
    未配置 serviceUrl -> unknown。队列 / 错误率 / 指标卡未接真实端点时返回空值。
    """
    del engine_key
    url = service_url.strip()
    connected = False
    latency_ms: float | None = None
    if url:
        connected, latency_ms = _probe_service(url)
        runtime_status = "running" if connected else "degraded"
    else:
        runtime_status = "unknown"
    return EngineRuntimeSnapshot(
        runtime_status=runtime_status,
        connected=connected,
        service_url=url,
        latency_ms=latency_ms,
        queue_depth=0,
        error_rate="",
        synced_at=datetime.now(UTC),
        metrics=[],
    )


def fetch_dependencies(engine_key: str) -> list[DependencyHealth]:
    """读取引擎外部依赖健康度。当前未约定真实端点，返回空集合。"""
    del engine_key
    return []


def fetch_logs(engine_key: str, level: str | None = None, limit: int = 100) -> list[EngineLogEntry]:
    """拉取引擎日志。当前未约定真实端点，返回空集合。"""
    del engine_key, level, limit
    return []


# ============================ 连接测试 / 运维操作 ============================


def test_connection(engine_key: str, service_url: str) -> EngineOpResult:
    """测试引擎服务连接：GET 引擎暴露的 serviceUrl，任意 HTTP 响应即视为在线并计时。"""
    if not service_url.strip():
        return _build_op_result(
            engine_key, "test_connection", "unknown", "未配置服务地址（connection_config.serviceUrl）", ok=False
        )
    reachable, latency = _probe_service(service_url)
    if reachable:
        message = f"连接正常 · {latency}ms" if latency is not None else "连接正常"
        return _build_op_result(engine_key, "test_connection", "running", message, ok=True)
    return _build_op_result(engine_key, "test_connection", "degraded", "服务不可达", ok=False)


# 以下运维操作映射到引擎暴露的控制 API（freqtrade /api/v1/* 或管理员配置的控制端点）。


def trigger_restart(engine_key: str, service_url: str, token: str = "", path: str = "") -> EngineOpResult:
    """重启引擎。必须显式配置 restartPath，避免误打未知控制端点。"""
    return _post_control(engine_key, "restart", service_url, token=token, path=path)


def reload_engine(
    engine_key: str, service_url: str, token: str = "", path: str = "/api/v1/reload_config"
) -> EngineOpResult:
    """热重载配置。默认兼容 Freqtrade ``/api/v1/reload_config``。"""
    return _post_control(engine_key, "reload", service_url, token=token, path=path)


def drain_engine(engine_key: str, service_url: str, token: str = "", path: str = "") -> EngineOpResult:
    """排空在途任务。必须显式配置 drainPath。"""
    return _post_control(engine_key, "drain", service_url, token=token, path=path)


def clear_queue_engine(engine_key: str, service_url: str, token: str = "", path: str = "") -> EngineOpResult:
    """清空队列。必须显式配置 clearQueuePath。"""
    return _post_control(engine_key, "clear_queue", service_url, token=token, path=path)


def emergency_stop_engine(
    engine_key: str, service_url: str, token: str = "", path: str = "/api/v1/stop"
) -> EngineOpResult:
    """紧急停机。默认兼容 Freqtrade ``/api/v1/stop``。"""
    return _post_control(engine_key, "emergency_stop", service_url, token=token, path=path)


def tear_down_engine(engine_key: str, service_url: str, token: str = "", path: str = "") -> EngineOpResult:
    """销毁并重建服务。必须显式配置 tearDownPath。"""
    return _post_control(engine_key, "tear_down", service_url, token=token, path=path)


def _build_op_result(
    engine_key: str, operation: str, runtime_status: str, message: str, ok: bool = True
) -> EngineOpResult:
    return EngineOpResult(
        ok=ok,
        engine_key=engine_key,
        operation=operation,
        runtime_status=runtime_status,
        message=message,
        executed_at=datetime.now(UTC),
    )
