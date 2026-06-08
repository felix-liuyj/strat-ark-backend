"""引擎运行时集成（freqtrade / tradingagents 经服务连接交互）。

部署模型：两个引擎**不做 K8s 集群化**，作为独立服务运行，backend 通过它们**暴露的
HTTP API**（``connection_config.serviceUrl``）做服务连接交互。监控为纯服务连接视图，不含
容器组 / 副本 / 主机资源等编排级概念。

- 连接 / 运行状态：``test_connection`` 与 ``fetch_runtime_snapshot`` 用 httpx 探测引擎
  serviceUrl（任意 HTTP 响应即视为在线并计时）；未配置 serviceUrl 或不可达时如实反映。
- 运营指标 / 依赖 / 日志：队列深度 / 错误率 / 指标卡 / 依赖健康 / 日志为引擎运营层数据，
  服务连接本身未必全部暴露，暂以确定性示意数据呈现，待引擎 API 暴露对应端点后再接真。
- 运维操作（restart / reload / stop 等）映射到引擎暴露的控制 API（如 freqtrade
  ``/api/v1/reload_config`` / ``/stop``），属引擎控制（交易执行相邻），保持预留 stub。

函数保持同步签名（调用方在 async ``before()`` 内同步调用），内部用 ``httpx.Client``。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

from libs.logger import logger

__all__ = (
    "DependencyHealth",
    "EngineLogEntry",
    "EngineOpResult",
    "EngineRuntimeSnapshot",
    "drain_engine",
    "emergency_stop_engine",
    "fetch_dependencies",
    "fetch_logs",
    "fetch_runtime_snapshot",
    "reload_engine",
    "scale_engine",
    "tear_down_engine",
    "test_connection",
    "trigger_redeploy",
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


# -- 两套引擎的确定性示意数据（serviceUrl 不可达时回退，与前端 data.ts 对齐）--

_ENGINE_PRESETS: dict[str, dict[str, object]] = {
    "freqtrade": {
        "queue_depth": 3,
        "error_rate": "0.02%",
        "metrics": [
            {"key": "托管 Bots · Containers", "value": "12", "detail": "9 Running · 3 Stopped"},
            {"key": "REST 请求 / 分", "value": "1,240", "detail": "P95 延迟 84ms"},
            {"key": "调度队列 · Queue", "value": "3", "detail": "回测 / 同步任务"},
            {"key": "错误率 · Error Rate", "value": "0.02%", "detail": "近 1h · 健康"},
        ],
        "deps": [
            ("Redis Queue", "db", "Healthy", None),
            ("PostgreSQL", "db", "Healthy", None),
            ("Binance API", "exchange", "Healthy", "12ms"),
            ("Bybit API", "exchange", "Degraded", "220ms"),
        ],
        "logs": [
            ("ok", "[orchestrator] heartbeat ok · 9 bots running · queue=3"),
            ("info", "[ft-bot-eth-02] entry signal ETH/USDT long · size=3.1 · mode=dry_run"),
            ("warn", "[risk] order blocked ETH/USDT · max_position_size 5.1% > 5%"),
            ("info", "[exchange] Bybit REST latency 220ms · marking degraded"),
            ("ok", "[orchestrator] bot started ft-bot-eth-02 · strategy=RSI-BB v3"),
        ],
    },
    "tradingagents": {
        "queue_depth": 6,
        "error_rate": "0.01%",
        "metrics": [
            {"key": "活跃 Agents", "value": "8", "detail": "全部在线"},
            {"key": "分析队列 · Queue", "value": "6", "detail": "等待调度"},
            {"key": "Tokens / 分", "value": "24.8K", "detail": "本月 4.8M / 10M"},
            {"key": "平均分析耗时", "value": "9.2s", "detail": "P95 14.6s"},
        ],
        "deps": [
            ("Model Gateway", "gateway", "Healthy", "Anthropic"),
            ("Redis Queue", "db", "Healthy", None),
            ("Market Data Feed", "feed", "Healthy", "2s 延迟"),
            ("Vector Store", "db", "Healthy", "pgvector"),
        ],
        "logs": [
            ("ok", "[api-cc03] analysis complete BTC/USDT 1h · conf=0.72 · 9.4s"),
            ("info", "[gateway] anthropic · 18,420 tokens · 200 OK"),
            ("info", "[api] dispatch market-analysis ETH/USDT to api-aa01"),
            ("ok", "[api-aa01] report agent_rpt_5521 persisted · pgvector"),
        ],
    },
}


def _preset(engine_key: str) -> dict[str, object]:
    return _ENGINE_PRESETS.get(engine_key, _ENGINE_PRESETS["freqtrade"])


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


# ============================ 监控读取（连接 / 状态经 serviceUrl 探活） ============================


def fetch_runtime_snapshot(engine_key: str, service_url: str = "") -> EngineRuntimeSnapshot:
    """读取引擎运行时聚合快照（服务连接视图）。

    经 serviceUrl 探活派生连接状态与延迟：可达 -> connected + running；不可达 -> degraded；
    未配置 serviceUrl -> unknown。队列 / 错误率 / 指标卡为运营层示意数据。
    """
    preset = _preset(engine_key)
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
        queue_depth=int(preset["queue_depth"]),  # type: ignore[arg-type]
        error_rate=str(preset["error_rate"]),
        synced_at=datetime.now(UTC),
        metrics=list(preset["metrics"]),  # type: ignore[arg-type]
    )


def fetch_dependencies(engine_key: str) -> list[DependencyHealth]:
    """读取引擎外部依赖健康度（示意数据，需引擎 API 暴露依赖探活后接真）。"""
    return [
        DependencyHealth(name=name, kind=kind, status=status, latency=latency)
        for name, kind, status, latency in _preset(engine_key)["deps"]  # type: ignore[union-attr]
    ]


def fetch_logs(engine_key: str, level: str | None = None, limit: int = 100) -> list[EngineLogEntry]:
    """拉取引擎日志（示意数据，需引擎 API 暴露日志端点后接真）。"""
    base = datetime.now(UTC)
    entries = [
        EngineLogEntry(timestamp=base - timedelta(minutes=3 * index), level=lvl, message=msg)
        for index, (lvl, msg) in enumerate(_preset(engine_key)["logs"])  # type: ignore[union-attr]
    ]
    if level and level.lower() != "all":
        entries = [entry for entry in entries if entry.level == level.lower()]
    return entries[:limit]


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


# 以下运维操作映射到引擎暴露的控制 API（freqtrade /api/v1/* 等），属引擎控制（交易执行相邻），
# 保持预留 stub、不发起真实控制请求。注释保留真实实现路径供后续按需接入。


def scale_engine(engine_key: str, replicas: int) -> EngineOpResult:
    """调整并发 / 实例数（stub）。服务连接模型下由引擎自身或其编排器处理。"""
    return _build_op_result(engine_key, "scale", "running", f"已提交调整 · 目标 {replicas}")


def trigger_restart(engine_key: str) -> EngineOpResult:
    """重启引擎（stub）。真实实现：调用引擎暴露的重启控制端点。"""
    return _build_op_result(engine_key, "restart", "running", "已触发重启")


def reload_engine(engine_key: str) -> EngineOpResult:
    """热重载配置（stub）。真实实现：调用引擎 reload 端点（如 freqtrade /api/v1/reload_config）。"""
    return _build_op_result(engine_key, "reload", "running", "配置已热重载")


def drain_engine(engine_key: str) -> EngineOpResult:
    """排空在途任务（stub）。真实实现：调用引擎暂停 / 排空端点。"""
    return _build_op_result(engine_key, "drain", "running", "已开始排空")


def trigger_redeploy(engine_key: str, image: str | None = None) -> EngineOpResult:
    """重新部署（stub）。真实实现：由服务编排器按新版本重建后再连。"""
    suffix = f" · {image}" if image else ""
    return _build_op_result(engine_key, "redeploy", "running", f"已开始重建{suffix}")


def emergency_stop_engine(engine_key: str) -> EngineOpResult:
    """紧急停机（stub，危险操作）。真实实现：调用引擎 stop 端点挂起运行任务。"""
    return _build_op_result(engine_key, "emergency_stop", "stopped", "已紧急停机")


def tear_down_engine(engine_key: str) -> EngineOpResult:
    """销毁并重建服务（stub，危险操作）。真实实现：由服务编排器销毁后按配置重建。"""
    return _build_op_result(engine_key, "tear_down", "running", "已开始重建服务")


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
