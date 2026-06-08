"""Kubernetes / 容器编排集成（引擎管理：只读监控接真 + 优雅回退）。

config 驱动的真实调用骨架 + 优雅回退：
- 真实路径（仅 in-cluster）：当 ``K8S_IN_CLUSTER`` 为真且容器内挂载了 serviceaccount
  token 时，用 httpx 调 K8s API server REST：
    - API base：``https://kubernetes.default.svc``
    - Bearer token：``/var/run/secrets/kubernetes.io/serviceaccount/token``
    - CA 证书：``/var/run/secrets/kubernetes.io/serviceaccount/ca.crt``（作为 TLS 校验根）
    - namespace：优先读 ``/var/run/secrets/kubernetes.io/serviceaccount/namespace``，
      回落 ``settings.K8S_NAMESPACE``
    - 列 Pod：``GET /api/v1/namespaces/{ns}/pods?labelSelector=app={deployment}``
    - 取 Deployment：``GET /apis/apps/v1/namespaces/{ns}/deployments/{deployment}``
  读到的运行时快照 / Pod 列表 / 副本数由真实集群状态派生。**需在 K8s 集群内运行 +
  serviceaccount 具备对应 namespace 的 pods / deployments 读权限（RBAC）方能联通。**
- 回退路径：非 in-cluster / 无 token / 任一请求失败，一律回退到原确定性拟真数据（与前端
  data.ts 对齐的两套引擎预置），保证本地与联调可用。

范围：本次仅监控读取（runtime_snapshot / pods / resources / dependencies / logs）接真；
资源用量（metrics-server）、依赖探测、Pod 日志读取需要额外后端（Prometheus / 集中日志），
in-cluster 也以确定性数据呈现。所有运维写操作（scale / restart / drain / redeploy /
emergency_stop / tear_down 等）属集群变更，保持 stub、不触碰真实集群。

函数保持同步签名（调用方在 async ``before()`` 内同步调用，不 await），内部真实路径用
``httpx.Client`` 同步客户端，不改变调用方契约。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from configs import get_settings
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

# in-cluster serviceaccount 标准挂载路径（容器内由 kubelet 自动注入）。
_SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
_TOKEN_PATH = f"{_SA_DIR}/token"
_CA_PATH = f"{_SA_DIR}/ca.crt"
_NAMESPACE_PATH = f"{_SA_DIR}/namespace"
_API_BASE = "https://kubernetes.default.svc"
_HTTP_TIMEOUT = 6.0


@dataclass(slots=True)
class PodInfo:
    """单个 Pod 运行时信息。"""

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
    """引擎运维操作结果（scale / restart / drain / redeploy 等）。"""

    ok: bool
    engine_key: str
    operation: str
    runtime_status: str
    message: str
    executed_at: datetime


# -- 预置两套引擎的拟真快照（回退数据，与前端 data.ts 对齐：freqtrade / tradingagents）--

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
        "deployment": "tradingagents-api",
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
            ("tradingagents-api-5f2a-aa01", "node-sg-2", "Running", "1.12", "1.8Gi", 0, "3d 2h"),
            ("tradingagents-api-5f2a-bb02", "node-sg-4", "Running", "0.98", "1.6Gi", 0, "3d 2h"),
            ("tradingagents-api-5f2a-cc03", "node-sg-1", "Running", "1.04", "1.7Gi", 0, "11h"),
            ("tradingagents-api-5f2a-dd04", "node-sg-3", "Scaling", "0.61", "1.1Gi", 0, "2m"),
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
            ("info", "[gateway] anthropic claude-sonnet · 18,420 tokens · 200 OK"),
            ("warn", "[hpa] queue depth 22 > 20 · scaling 3 → 4 replicas"),
            ("info", "[api] dispatch market-analysis ETH/USDT to api-aa01"),
            ("ok", "[api-aa01] report agent_rpt_5521 persisted · pgvector"),
        ],
    },
}


def _preset(engine_key: str) -> dict[str, object]:
    return _ENGINE_PRESETS.get(engine_key, _ENGINE_PRESETS["freqtrade"])


# ============================ in-cluster 真实访问工具 ============================


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _in_cluster_token() -> str | None:
    """仅当配置开启 in-cluster 且 token 文件存在时返回 Bearer token，否则 None（走回退）。"""
    if not getattr(get_settings(), "K8S_IN_CLUSTER", False):
        return None
    token = _read_text(_TOKEN_PATH)
    return token or None


def _namespace() -> str:
    """优先用 serviceaccount 注入的 namespace 文件，回落 settings.K8S_NAMESPACE。"""
    return _read_text(_NAMESPACE_PATH) or getattr(get_settings(), "K8S_NAMESPACE", "stratark-prod")


def _verify() -> str | bool:
    """TLS 校验：存在挂载的 CA 证书则用其作为根，否则退回 httpx 默认校验。"""
    return _CA_PATH if os.path.exists(_CA_PATH) else True


def _api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """向 K8s API server 发起带 Bearer token 的 GET。无 token 时返回 None（不发请求）。"""
    token = _in_cluster_token()
    if token is None:
        return None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    with httpx.Client(timeout=_HTTP_TIMEOUT, verify=_verify()) as client:
        response = client.get(f"{_API_BASE}{path}", params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _deployment_name(engine_key: str) -> str:
    return str(_preset(engine_key)["deployment"])


def _format_uptime(start_time: str | None) -> str:
    """ISO8601 启动时间 -> 紧凑 uptime 文案（如 ``6d 4h`` / ``11h`` / ``2m``）。"""
    if not start_time:
        return "-"
    try:
        started = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except ValueError:
        return "-"
    delta = datetime.now(UTC) - started
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes = remainder // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _pod_from_item(item: dict[str, Any]) -> PodInfo:
    """K8s Pod 对象 -> PodInfo（资源用量需 metrics-server，此处留占位 ``-``）。"""
    metadata = item.get("metadata", {})
    spec = item.get("spec", {})
    status = item.get("status", {})
    container_statuses = status.get("containerStatuses", []) or []
    restarts = sum(int(cs.get("restartCount", 0) or 0) for cs in container_statuses)
    return PodInfo(
        name=str(metadata.get("name", "")),
        node=str(spec.get("nodeName", "") or "-"),
        status=str(status.get("phase", "Unknown")),
        cpu="-",
        mem="-",
        restarts=restarts,
        uptime=_format_uptime(status.get("startTime")),
    )


# ============================ 监控读取（真实路径失败回退 demo） ============================


def fetch_runtime_snapshot(engine_key: str) -> EngineRuntimeSnapshot:
    """读取引擎运行时聚合快照。

    真实路径（in-cluster）：读 Deployment ``status`` 取 replicas / readyReplicas，运行状态
    由就绪副本数派生（队列深度 / 错误率 / 指标卡需指标后端，仍以确定性数据补全）。
    无 token / 失败时回退确定性数据。
    """
    preset = _preset(engine_key)
    try:
        ns = _namespace()
        data = _api_get(f"/apis/apps/v1/namespaces/{ns}/deployments/{_deployment_name(engine_key)}")
        if isinstance(data, dict) and data.get("status") is not None:
            status = data["status"]
            desired = int(status.get("replicas", preset["replicas_desired"]) or 0)  # type: ignore[arg-type]
            ready = int(status.get("readyReplicas", 0) or 0)
            runtime_status = "running" if ready > 0 and ready >= desired else "degraded"
            return EngineRuntimeSnapshot(
                runtime_status=runtime_status,
                replicas_desired=desired,
                replicas_ready=ready,
                queue_depth=int(preset["queue_depth"]),  # type: ignore[arg-type]
                error_rate=str(preset["error_rate"]),
                synced_at=datetime.now(UTC),
                metrics=list(preset["metrics"]),  # type: ignore[arg-type]
            )
    except Exception as exc:
        logger.warning(f"kubernetes.fetch_runtime_snapshot fallback to demo: {exc}")
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
    """列出引擎 Pod。

    真实路径（in-cluster）：``GET /api/v1/namespaces/{ns}/pods`` 按 ``app={deployment}``
    label selector 过滤。无 token / 失败 / 空结果时回退确定性数据。
    """
    try:
        ns = _namespace()
        data = _api_get(
            f"/api/v1/namespaces/{ns}/pods",
            {"labelSelector": f"app={_deployment_name(engine_key)}"},
        )
        if isinstance(data, dict):
            items = data.get("items", [])
            if isinstance(items, list) and items:
                return [_pod_from_item(item) for item in items]
    except Exception as exc:
        logger.warning(f"kubernetes.fetch_pods fallback to demo: {exc}")
    return [
        PodInfo(name=name, node=node, status=status, cpu=cpu, mem=mem, restarts=restarts, uptime=uptime)
        for name, node, status, cpu, mem, restarts, uptime in _preset(engine_key)["pods"]  # type: ignore[union-attr]
    ]


def fetch_resources(engine_key: str) -> list[ResourceUsage]:
    """读取引擎资源用量（确定性数据）。

    真实用量需 metrics-server / Prometheus（``GET /apis/metrics.k8s.io/v1beta1/...``），
    非核心 K8s API、依赖额外组件，本次不接真，统一返回确定性数据。
    """
    return [
        ResourceUsage(label=label, percent=percent, value=value)
        for label, percent, value in _preset(engine_key)["resources"]  # type: ignore[union-attr]
    ]


def fetch_dependencies(engine_key: str) -> list[DependencyHealth]:
    """读取引擎外部依赖健康度（确定性数据）。

    真实探测需逐一连 Redis / PG / 网关 / 行情源（跨服务、各异），不在 K8s API 范围内，
    本次不接真，统一返回确定性数据。
    """
    return [
        DependencyHealth(name=name, kind=kind, status=status, latency=latency)
        for name, kind, status, latency in _preset(engine_key)["deps"]  # type: ignore[union-attr]
    ]


def fetch_logs(engine_key: str, level: str | None = None, limit: int = 100) -> list[PodLogEntry]:
    """拉取引擎日志（确定性数据）。

    真实 Pod 日志为纯文本流（``GET .../pods/{pod}/log``，非结构化、无 level 字段），与本
    DTO 的结构化级别不直接对应，需集中式日志后端解析，本次不接真，统一返回确定性数据。
    """
    base = datetime.now(UTC)
    entries = [
        PodLogEntry(timestamp=base - timedelta(minutes=3 * index), level=lvl, message=msg)
        for index, (lvl, msg) in enumerate(_preset(engine_key)["logs"])  # type: ignore[union-attr]
    ]
    if level and level.lower() != "all":
        entries = [entry for entry in entries if entry.level == level.lower()]
    return entries[:limit]


# ============================ 运维写操作（stub，集群变更不接真） ============================
# 以下均为集群变更类操作（patch / rollout / scale / 删除重建），属危险操作，保持 stub，
# 不触碰真实集群、不执行真实运维。注释保留真实实现路径供后续按需接入。


def test_connection(engine_key: str, service_url: str) -> EngineOpResult:
    """测试引擎内网连接（stub）。真实实现：请求引擎健康检查端点并计时。"""
    return _build_op_result(engine_key, "test_connection", "running", "连接正常 · 84ms")


def scale_engine(engine_key: str, replicas: int) -> EngineOpResult:
    """扩缩容（stub）。真实实现：patch Deployment.spec.replicas。"""
    return _build_op_result(engine_key, "scale", "running", f"已提交扩缩容 · 目标 {replicas} 副本")


def trigger_restart(engine_key: str) -> EngineOpResult:
    """滚动重启（stub）。真实实现：patch rollout restart 注解逐个重建 Pod。"""
    return _build_op_result(engine_key, "restart", "running", "已触发滚动重启")


def reload_engine(engine_key: str) -> EngineOpResult:
    """热重载配置（stub）。真实实现：调用引擎 reload 端点或重载 ConfigMap。"""
    return _build_op_result(engine_key, "reload", "running", "配置已热重载")


def drain_engine(engine_key: str) -> EngineOpResult:
    """排空并重新调度（stub）。真实实现：cordon + drain 节点后重新调度。"""
    return _build_op_result(engine_key, "drain", "running", "已开始排空")


def trigger_redeploy(engine_key: str, image: str | None = None) -> EngineOpResult:
    """拉取镜像并重建（stub）。真实实现：更新镜像标签触发滚动发布。"""
    suffix = f" · {image}" if image else ""
    return _build_op_result(engine_key, "redeploy", "running", f"已开始重建{suffix}")


def emergency_stop_engine(engine_key: str) -> EngineOpResult:
    """紧急停机（stub，危险操作）。真实实现：将副本缩为 0 并挂起运行任务。"""
    return _build_op_result(engine_key, "emergency_stop", "stopped", "已紧急停机")


def tear_down_engine(engine_key: str) -> EngineOpResult:
    """销毁并重建服务（stub，危险操作）。真实实现：删除 Deployment 后按配置重建。"""
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
