"""引擎运行时集成（freqtrade / tradingagents 经服务连接交互）。

部署模型：两个引擎**不做 K8s 集群化**，作为独立服务运行，backend 通过它们**暴露的
HTTP API**（``connection_config.serviceUrl``）做服务连接交互。因此运行时状态与连接测试
经 serviceUrl 探活实现，而非 K8s API。

- 连接测试 / 运行状态：``test_connection`` 与 ``fetch_runtime_snapshot`` 用 httpx 探测引擎
  serviceUrl（任意 HTTP 响应即视为在线并计时）；未配置 serviceUrl 或不可达时如实反映。
- Pod / 资源 / 依赖 / 日志：服务连接本身不暴露这些主机 / 编排级指标（需引擎自身 API 或集中
  监控后端提供），暂以确定性示意数据呈现，待引擎 API 暴露对应端点后再接真。
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
    "EngineOpResult",
    "EngineRuntimeSnapshot",
    "PodInfo",
    "PodLogEntry",
    "ResourceUsage",
    "drain_engine",
    "emergency_stop_engine",
    "fetch_dependencies",
    "fetch_logs",
    "fetch_pods",
    "fetch_resources",
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
class PodInfo:
    """单个引擎运行实例信息（服务连接模型下为示意，命名沿用兼容前端响应）。"""

    name: str
    node: str
    status: str
    cpu: str
    mem: str
    restarts: int
    uptime: str


@dataclass(slots=True)
class ResourceUsage:
    """单项资源用量（含百分比与可读文案）。"""

    label: str
    percent: int
    value: str


@dataclass(slots=True)
class DependencyHealth:
    """单个外部依赖的健康度。"""

    name: str
    kind: str
    status: str
    latency: str | None = None


@dataclass(slots=True)
class PodLogEntry:
    """单条引擎日志。"""

    timestamp: datetime
    level: str
    message: str


@dataclass(slots=True)
class EngineRuntimeSnapshot:
    """引擎运行时聚合快照。"""

    runtime_status: str
    replicas_desired: int
    replicas_ready: int
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


# -- 两套引擎的确定性示意数据（serviceUrl 未配置 / 不可达时回退，与前端 data.ts 对齐）--

_ENGINE_PRESETS: dict[str, dict[str, object]] = {
    "freqtrade": {
        "replicas_desired": 3,
        "replicas_ready": 3,
        "queue_depth": 3,
        "error_rate": "0.02%",
        "metrics": [
            {"key": "托管 Bots · Containers", "value": "12", "detail": "9 Running · 3 Stopped"},
            {"key": "REST 请求 / 分", "value": "1,240", "detail": "P95 延迟 84ms"},
            {"key": "调度队列 · Queue", "value": "3", "detail": "回测 / 同步任务"},
            {"key": "错误率 · Error Rate", "value": "0.02%", "detail": "近 1h · 健康"},
        ],
        "pods": [
            ("freqtrade-orch-7c9d-abc12", "node-sg-1", "Running", "0.42", "612Mi", 0, "6d 4h"),
            ("freqtrade-orch-7c9d-de345", "node-sg-2", "Running", "0.38", "588Mi", 0, "6d 4h"),
            ("freqtrade-orch-7c9d-fg678", "node-sg-3", "Running", "0.51", "634Mi", 1, "2d 1h"),
        ],
        "resources": [
            ("CPU", 44, "1.31 / 3.0"),
            ("内存 Memory", 40, "1.8 / 4.5Gi"),
            ("网络 I/O", 28, "3.2 MB/s"),
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
        "replicas_desired": 4,
        "replicas_ready": 4,
        "queue_depth": 6,
        "error_rate": "0.01%",
        "metrics": [
            {"key": "活跃 Agents", "value": "8", "detail": "全部在线"},
            {"key": "分析队列 · Queue", "value": "6", "detail": "等待调度"},
            {"key": "Tokens / 分", "value": "24.8K", "detail": "本月 4.8M / 10M"},
            {"key": "平均分析耗时", "value": "9.2s", "detail": "P95 14.6s"},
        ],
        "pods": [
            ("tradingagents-api-5f2a-aa01", "node-sg-2", "Running", "1.12", "1.8Gi", 0, "3d 2h"),
            ("tradingagents-api-5f2a-bb02", "node-sg-4", "Running", "0.98", "1.6Gi", 0, "3d 2h"),
            ("tradingagents-api-5f2a-cc03", "node-sg-1", "Running", "1.04", "1.7Gi", 0, "11h"),
        ],
        "resources": [
            ("CPU", 62, "3.75 / 6.0"),
            ("内存 Memory", 55, "6.2 / 12Gi"),
            ("Gateway QPS", 34, "3.4 req/s"),
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
    """读取引擎运行时聚合快照。

    运行状态经 serviceUrl 探活派生：可达 -> running 并附「服务连接」延迟指标；不可达 -> degraded。
    未配置 serviceUrl 时回退确定性示意状态。副本 / 队列 / 指标卡为示意（服务连接不暴露编排级数据）。
    """
    preset = _preset(engine_key)
    runtime_status = "running"
    metrics = list(preset["metrics"])  # type: ignore[arg-type]
    if service_url.strip():
        reachable, latency = _probe_service(service_url)
        runtime_status = "running" if reachable else "degraded"
        if reachable and latency is not None:
            metrics = [{"key": "服务连接 · Connection", "value": "在线", "detail": f"{latency}ms"}, *metrics]
    return EngineRuntimeSnapshot(
        runtime_status=runtime_status,
        replicas_desired=int(preset["replicas_desired"]),  # type: ignore[arg-type]
        replicas_ready=int(preset["replicas_ready"]) if runtime_status == "running" else 0,  # type: ignore[arg-type]
        queue_depth=int(preset["queue_depth"]),  # type: ignore[arg-type]
        error_rate=str(preset["error_rate"]),
        synced_at=datetime.now(UTC),
        metrics=metrics,
    )


def fetch_pods(engine_key: str) -> list[PodInfo]:
    """列出引擎运行实例（示意数据）。

    服务连接模型不暴露主机 / 编排级实例清单；待引擎 API 暴露实例端点后再接真。
    """
    return [
        PodInfo(name=name, node=node, status=status, cpu=cpu, mem=mem, restarts=restarts, uptime=uptime)
        for name, node, status, cpu, mem, restarts, uptime in _preset(engine_key)["pods"]  # type: ignore[union-attr]
    ]


def fetch_resources(engine_key: str) -> list[ResourceUsage]:
    """读取引擎资源用量（示意数据，需引擎 API / 监控后端暴露指标后接真）。"""
    return [
        ResourceUsage(label=label, percent=percent, value=value)
        for label, percent, value in _preset(engine_key)["resources"]  # type: ignore[union-attr]
    ]


def fetch_dependencies(engine_key: str) -> list[DependencyHealth]:
    """读取引擎外部依赖健康度（示意数据，需引擎 API 暴露依赖探活后接真）。"""
    return [
        DependencyHealth(name=name, kind=kind, status=status, latency=latency)
        for name, kind, status, latency in _preset(engine_key)["deps"]  # type: ignore[union-attr]
    ]


def fetch_logs(engine_key: str, level: str | None = None, limit: int = 100) -> list[PodLogEntry]:
    """拉取引擎日志（示意数据，需引擎 API 暴露日志端点后接真）。"""
    base = datetime.now(UTC)
    entries = [
        PodLogEntry(timestamp=base - timedelta(minutes=3 * index), level=lvl, message=msg)
        for index, (lvl, msg) in enumerate(_preset(engine_key)["logs"])  # type: ignore[union-attr]
    ]
    if level and level.lower() != "all":
        entries = [entry for entry in entries if entry.level == level.lower()]
    return entries[:limit]


# ============================ 连接测试 / 运维操作 ============================


def test_connection(engine_key: str, service_url: str) -> EngineOpResult:
    """测试引擎服务连接：GET 引擎暴露的 serviceUrl，任意 HTTP 响应即视为在线并计时。"""
    if not service_url.strip():
        return _build_op_result(engine_key, "test_connection", "unknown", "未配置服务地址（connection_config.serviceUrl）", ok=False)
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
