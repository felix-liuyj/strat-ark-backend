"""Kubernetes / 容器编排集成 stub（引擎管理专用）。

返回拟真 mock 数据；函数签名按真实集群运维预留：真实实现时这里会调用 Kubernetes
API（Deployment/Pod/HPA 读写、scale/restart/drain/redeploy、紧急停机与销毁重建），
以及引擎自身的内网 REST 健康检查端点。当前阶段不触碰任何真实集群、不执行任何真实
运维操作，Pod / 资源 / 依赖 / 日志全为模拟。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

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


@dataclass(slots=True)
class PodInfo:
    """单个 Pod 运行时信息（mock）。"""

    name: str
    node: str
    status: str
    cpu: str
    mem: str
    restarts: int
    uptime: str


@dataclass(slots=True)
class ResourceUsage:
    """单项资源用量（mock，含百分比与可读文案）。"""

    label: str
    percent: int
    value: str


@dataclass(slots=True)
class DependencyHealth:
    """单个外部依赖的健康度（mock）。"""

    name: str
    kind: str
    status: str
    latency: str | None = None


@dataclass(slots=True)
class PodLogEntry:
    """单条引擎日志（mock）。"""

    timestamp: datetime
    level: str
    message: str


@dataclass(slots=True)
class EngineRuntimeSnapshot:
    """引擎运行时聚合快照（mock）。"""

    runtime_status: str
    replicas_desired: int
    replicas_ready: int
    queue_depth: int
    error_rate: str
    synced_at: datetime
    metrics: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class EngineOpResult:
    """引擎运维操作结果（scale / restart / drain / redeploy 等）。"""

    ok: bool
    engine_key: str
    operation: str
    runtime_status: str
    message: str
    executed_at: datetime


# -- 预置两套引擎的拟真快照（与前端 data.ts 对齐：freqtrade / tradingagents）--

_ENGINE_PRESETS: dict[str, dict[str, object]] = {
    "freqtrade": {
        "deployment": "freqtrade-orchestrator",
        "namespace": "stratark-prod",
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
        "deployment": "tradingagents-worker",
        "namespace": "stratark-prod",
        "replicas_desired": 4,
        "replicas_ready": 4,
        "queue_depth": 6,
        "error_rate": "0.01%",
        "metrics": [
            {"key": "活跃 Agents", "value": "8", "detail": "全部在线"},
            {"key": "分析队列 · Queue", "value": "6", "detail": "触发 HPA 扩容"},
            {"key": "Tokens / 分", "value": "24.8K", "detail": "本月 4.8M / 10M"},
            {"key": "平均分析耗时", "value": "9.2s", "detail": "P95 14.6s"},
        ],
        "pods": [
            ("tradingagents-wk-5f2a-aa01", "node-sg-2", "Running", "1.12", "1.8Gi", 0, "3d 2h"),
            ("tradingagents-wk-5f2a-bb02", "node-sg-4", "Running", "0.98", "1.6Gi", 0, "3d 2h"),
            ("tradingagents-wk-5f2a-cc03", "node-sg-1", "Running", "1.04", "1.7Gi", 0, "11h"),
            ("tradingagents-wk-5f2a-dd04", "node-sg-3", "Scaling", "0.61", "1.1Gi", 0, "2m"),
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
            ("ok", "[worker-cc03] analysis complete BTC/USDT 1h · conf=0.72 · 9.4s"),
            ("info", "[gateway] anthropic claude-sonnet · 18,420 tokens · 200 OK"),
            ("warn", "[hpa] queue depth 22 > 20 · scaling 3 → 4 replicas"),
            ("info", "[orchestrator] dispatch market-analysis ETH/USDT to worker-aa01"),
            ("ok", "[worker-aa01] report agent_rpt_5521 persisted · pgvector"),
        ],
    },
}


def _preset(engine_key: str) -> dict[str, object]:
    return _ENGINE_PRESETS.get(engine_key, _ENGINE_PRESETS["freqtrade"])


def fetch_runtime_snapshot(engine_key: str) -> EngineRuntimeSnapshot:
    """读取引擎运行时聚合快照（mock）。真实实现：聚合 Deployment status + 指标后端。"""
    preset = _preset(engine_key)
    return EngineRuntimeSnapshot(
        runtime_status="running",
        replicas_desired=int(preset["replicas_desired"]),  # type: ignore[arg-type]
        replicas_ready=int(preset["replicas_ready"]),  # type: ignore[arg-type]
        queue_depth=int(preset["queue_depth"]),  # type: ignore[arg-type]
        error_rate=str(preset["error_rate"]),
        synced_at=datetime.now(UTC),
        metrics=list(preset["metrics"]),  # type: ignore[arg-type]
    )


def fetch_pods(engine_key: str) -> list[PodInfo]:
    """列出引擎 Pod（mock）。真实实现：调用 K8s API 按 label selector 查询 Pod。"""
    return [
        PodInfo(name=name, node=node, status=status, cpu=cpu, mem=mem, restarts=restarts, uptime=uptime)
        for name, node, status, cpu, mem, restarts, uptime in _preset(engine_key)["pods"]  # type: ignore[union-attr]
    ]


def fetch_resources(engine_key: str) -> list[ResourceUsage]:
    """读取引擎资源用量（mock）。真实实现：读取 metrics-server / Prometheus。"""
    return [
        ResourceUsage(label=label, percent=percent, value=value)
        for label, percent, value in _preset(engine_key)["resources"]  # type: ignore[union-attr]
    ]


def fetch_dependencies(engine_key: str) -> list[DependencyHealth]:
    """读取引擎外部依赖健康度（mock）。真实实现：探测 Redis/PG/网关/行情源等。"""
    return [
        DependencyHealth(name=name, kind=kind, status=status, latency=latency)
        for name, kind, status, latency in _preset(engine_key)["deps"]  # type: ignore[union-attr]
    ]


def fetch_logs(engine_key: str, level: str | None = None, limit: int = 100) -> list[PodLogEntry]:
    """拉取引擎日志（mock）。真实实现：读取 Pod stdout 或集中式日志后端。"""
    base = datetime.now(UTC)
    entries = [
        PodLogEntry(timestamp=base - timedelta(minutes=3 * index), level=lvl, message=msg)
        for index, (lvl, msg) in enumerate(_preset(engine_key)["logs"])  # type: ignore[union-attr]
    ]
    if level and level.lower() != "all":
        entries = [entry for entry in entries if entry.level == level.lower()]
    return entries[:limit]


def test_connection(engine_key: str, service_url: str) -> EngineOpResult:
    """测试引擎内网连接（mock）。真实实现：请求引擎健康检查端点并计时。"""
    return _build_op_result(engine_key, "test_connection", "running", "连接正常 · 84ms")


def scale_engine(engine_key: str, replicas: int) -> EngineOpResult:
    """扩缩容（mock）。真实实现：patch Deployment.spec.replicas。"""
    return _build_op_result(engine_key, "scale", "running", f"已提交扩缩容 · 目标 {replicas} 副本")


def trigger_restart(engine_key: str) -> EngineOpResult:
    """滚动重启（mock）。真实实现：patch rollout restart 注解逐个重建 Pod。"""
    return _build_op_result(engine_key, "restart", "running", "已触发滚动重启")


def reload_engine(engine_key: str) -> EngineOpResult:
    """热重载配置（mock）。真实实现：调用引擎 reload 端点或重载 ConfigMap。"""
    return _build_op_result(engine_key, "reload", "running", "配置已热重载")


def drain_engine(engine_key: str) -> EngineOpResult:
    """排空并重新调度（mock）。真实实现：cordon + drain 节点后重新调度。"""
    return _build_op_result(engine_key, "drain", "running", "已开始排空")


def trigger_redeploy(engine_key: str, image: str | None = None) -> EngineOpResult:
    """拉取镜像并重建（mock）。真实实现：更新镜像标签触发滚动发布。"""
    suffix = f" · {image}" if image else ""
    return _build_op_result(engine_key, "redeploy", "running", f"已开始重建{suffix}")


def emergency_stop_engine(engine_key: str) -> EngineOpResult:
    """紧急停机（mock，危险操作）。真实实现：将副本缩为 0 并挂起运行任务。"""
    return _build_op_result(engine_key, "emergency_stop", "stopped", "已紧急停机")


def tear_down_engine(engine_key: str) -> EngineOpResult:
    """销毁并重建服务（mock，危险操作）。真实实现：删除 Deployment 后按配置重建。"""
    return _build_op_result(engine_key, "tear_down", "running", "已开始重建服务")


def _build_op_result(engine_key: str, operation: str, runtime_status: str, message: str) -> EngineOpResult:
    return EngineOpResult(
        ok=True,
        engine_key=engine_key,
        operation=operation,
        runtime_status=runtime_status,
        message=message,
        executed_at=datetime.now(UTC),
    )
