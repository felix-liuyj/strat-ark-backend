"""引擎管理 view models（管理员专属）。

覆盖：引擎列表、监控聚合（service stub 读 K8s）、连接配置读写（凭证掩码）、部署配置读写、
运维操作执行（engine_ops 记录 + 危险操作写平台审计）、运维流水查询。
"""

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.engine import (
    EngineConnectionUpdateForm,
    EngineDeploymentUpdateForm,
    EngineOpExecuteForm,
)
from libs.audit.service import AuditLogService
from libs.auth.permissions import PermissionChecker
from libs.integrations import kubernetes
from models.account import UserTypeEnum
from models.audit_log import ActorTypeEnum, AuditActionEnum, AuditCategoryEnum, AuditStatusEnum
from models.engine import (
    DANGEROUS_OP_TYPES,
    Engine,
    EngineKindEnum,
    EngineOp,
    EngineOpStatusEnum,
    EngineOpTypeEnum,
    EngineStatusEnum,
)
from responses.engine import (
    DependencyResponseData,
    EngineConnectionResponseData,
    EngineDeploymentResponseData,
    EngineLogResponseData,
    EngineMonitorResponseData,
    EngineOpResponseData,
    EngineResponseData,
    PodResponseData,
    ResourceUsageResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = (
    "ExecuteEngineOpViewModel",
    "GetEngineConnectionViewModel",
    "GetEngineDeploymentViewModel",
    "GetEngineMonitorViewModel",
    "ListEngineOpsViewModel",
    "ListEnginesViewModel",
    "UpdateEngineConnectionViewModel",
    "UpdateEngineDeploymentViewModel",
)

# 连接 / 部署配置中需要掩码后才能回显的敏感字段。
_SENSITIVE_CONFIG_KEYS = frozenset({"token", "apiKey", "secret", "restApiToken", "password"})
_MASK_VALUE = "***"

# 引擎默认元数据（首次访问时按类型 seed，与前端 data.ts 对齐）。
_ENGINE_DEFAULTS: dict[EngineKindEnum, dict[str, Any]] = {
    EngineKindEnum.FREQTRADE: {
        "name": "Freqtrade 执行引擎",
        "deployment_name": "freqtrade-orchestrator",
        "replicas_desired": 3,
        "connection_config": {
            "serviceUrl": "http://freqtrade-orchestrator.stratark-prod.svc.cluster.local:8080",
            "healthPath": "/api/v1/ping",
            "restApiToken": "ft_tok_secret_3f9a",
            "timeout": 30,
            "retries": 3,
            "mtls": True,
        },
        "deployment_config": {
            "image": "stratark/freqtrade-orchestrator:2026.4.2",
            "replicas": 3,
            "scheduler": 8,
            "cpuLimit": "1",
            "memLimit": "1.5Gi",
            "dataVolume": "50Gi",
            "logLevel": "INFO",
            "hpaEnabled": True,
            "hpaMin": 3,
            "hpaMax": 6,
            "hpaTargetCpu": 70,
        },
    },
    EngineKindEnum.TRADINGAGENTS: {
        "name": "TradingAgents 投研引擎",
        "deployment_name": "tradingagents-worker",
        "replicas_desired": 4,
        "connection_config": {
            "serviceUrl": "http://tradingagents-worker.stratark-prod.svc.cluster.local:9100",
            "redisUrl": "redis://redis.stratark-prod.svc:6379/2",
            "vectorStore": "postgres://pgvector.stratark-prod:5432/agents",
            "marketFeed": "wss://market-feed.stratark-prod.svc:7000",
            "timeout": 60,
            "gatewayProvider": "Anthropic",
            "gatewayEndpoint": "https://api.anthropic.com",
            "apiKey": "sk-ant-secret-7f3a",
        },
        "deployment_config": {
            "image": "stratark/tradingagents-worker:2026.4.0",
            "replicas": 4,
            "concurrency": 8,
            "cpuLimit": "1.5",
            "memLimit": "3Gi",
            "logLevel": "INFO",
            "temperature": 0.3,
            "maxTokens": 4096,
            "hpaEnabled": True,
            "hpaMin": 2,
            "hpaMax": 6,
            "hpaTargetQueueDepth": 20,
        },
    },
}


def _mask_config(config: dict[str, Any]) -> dict[str, Any]:
    """对配置中的敏感字段做掩码，避免明文回显。"""
    masked: dict[str, Any] = {}
    for key, value in config.items():
        masked[key] = _MASK_VALUE if key in _SENSITIVE_CONFIG_KEYS and value else value
    return masked


def _merge_config(stored: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """合并配置：掩码占位（***）字段不覆盖已存值。"""
    merged = dict(stored or {})
    for key, value in incoming.items():
        if value == _MASK_VALUE:
            continue
        merged[key] = value
    return merged


def _build_engine(engine: Engine) -> EngineResponseData:
    return EngineResponseData(
        id=engine.id,
        engineKind=engine.engine_kind,
        name=engine.name,
        namespace=engine.namespace,
        deploymentName=engine.deployment_name,
        status=engine.status,
        replicasDesired=engine.replicas_desired,
    )


def _build_op(op: EngineOp) -> EngineOpResponseData:
    return EngineOpResponseData(
        id=op.id,
        engineKind=op.engine_kind,
        opType=op.op_type,
        status=op.status,
        message=op.message,
        operatorId=op.operator_id,
        detail=op.detail or {},
        createdAt=op.created_at,
    )


class _AdminEngineViewModel(BaseViewModel):
    """引擎域共享基类：统一管理员校验 + 引擎按类型 seed / 获取。"""

    checker: PermissionChecker
    db: AsyncSession

    def _require_admin(self) -> bool:
        self.checker.require_auth()
        if self.checker.user_type != UserTypeEnum.ADMIN:
            self.forbidden("仅管理员可访问")
            return False
        return True

    async def _get_or_seed_engine(self, engine_kind: EngineKindEnum) -> Engine:
        engine = await self.db.scalar(select(Engine).where(Engine.engine_kind == engine_kind))
        if engine is not None:
            return engine
        defaults = _ENGINE_DEFAULTS[engine_kind]
        engine = Engine(
            engine_kind=engine_kind,
            name=str(defaults["name"]),
            namespace="stratark-prod",
            deployment_name=str(defaults["deployment_name"]),
            status=EngineStatusEnum.RUNNING,
            replicas_desired=int(defaults["replicas_desired"]),  # type: ignore[arg-type]
            connection_config=dict(defaults["connection_config"]),  # type: ignore[arg-type]
            deployment_config=dict(defaults["deployment_config"]),  # type: ignore[arg-type]
        )
        self.db.add(engine)
        await self.db.commit()
        await self.db.refresh(engine)
        return engine


class ListEnginesViewModel(_AdminEngineViewModel):
    """引擎列表（首次访问自动 seed 两套引擎）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        engines = [await self._get_or_seed_engine(kind) for kind in EngineKindEnum]
        self.operating_successfully([_build_engine(engine) for engine in engines])


class GetEngineMonitorViewModel(_AdminEngineViewModel):
    """引擎监控聚合（service stub 读 K8s）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        engine_kind: EngineKindEnum,
        log_level: str | None,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.engine_kind = engine_kind
        self.log_level = log_level
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        await self._get_or_seed_engine(self.engine_kind)

        key = str(self.engine_kind)
        snapshot = kubernetes.fetch_runtime_snapshot(key)
        pods = kubernetes.fetch_pods(key)
        resources = kubernetes.fetch_resources(key)
        deps = kubernetes.fetch_dependencies(key)
        logs = kubernetes.fetch_logs(key, level=self.log_level)

        self.operating_successfully(
            EngineMonitorResponseData(
                engineKind=self.engine_kind,
                runtimeStatus=snapshot.runtime_status,
                replicasReady=snapshot.replicas_ready,
                replicasDesired=snapshot.replicas_desired,
                queueDepth=snapshot.queue_depth,
                errorRate=snapshot.error_rate,
                syncedAt=snapshot.synced_at,
                metrics=snapshot.metrics,
                pods=[
                    PodResponseData(
                        name=pod.name,
                        node=pod.node,
                        status=pod.status,
                        cpu=pod.cpu,
                        mem=pod.mem,
                        restarts=pod.restarts,
                        uptime=pod.uptime,
                    )
                    for pod in pods
                ],
                resources=[
                    ResourceUsageResponseData(label=res.label, percent=res.percent, value=res.value)
                    for res in resources
                ],
                dependencies=[
                    DependencyResponseData(name=dep.name, kind=dep.kind, status=dep.status, latency=dep.latency)
                    for dep in deps
                ],
                logs=[
                    EngineLogResponseData(timestamp=log.timestamp, level=log.level, message=log.message)
                    for log in logs
                ],
            )
        )


class GetEngineConnectionViewModel(_AdminEngineViewModel):
    """读取连接配置（凭证掩码）。"""

    def __init__(
        self, request: Request, db: AsyncSession, engine_kind: EngineKindEnum, checker: PermissionChecker
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.engine_kind = engine_kind
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        engine = await self._get_or_seed_engine(self.engine_kind)
        self.operating_successfully(
            EngineConnectionResponseData(
                engineKind=engine.engine_kind,
                config=_mask_config(engine.connection_config or {}),
            )
        )


class UpdateEngineConnectionViewModel(_AdminEngineViewModel):
    """写入连接配置（掩码占位字段不覆盖已存凭证）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        engine_kind: EngineKindEnum,
        form: EngineConnectionUpdateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.engine_kind = engine_kind
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        engine = await self._get_or_seed_engine(self.engine_kind)
        engine.connection_config = _merge_config(engine.connection_config, self.form.config)
        await self.db.commit()
        await self.db.refresh(engine)
        self.operating_successfully(
            EngineConnectionResponseData(
                engineKind=engine.engine_kind,
                config=_mask_config(engine.connection_config or {}),
            )
        )


class GetEngineDeploymentViewModel(_AdminEngineViewModel):
    """读取部署配置。"""

    def __init__(
        self, request: Request, db: AsyncSession, engine_kind: EngineKindEnum, checker: PermissionChecker
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.engine_kind = engine_kind
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        engine = await self._get_or_seed_engine(self.engine_kind)
        self.operating_successfully(
            EngineDeploymentResponseData(
                engineKind=engine.engine_kind,
                replicasDesired=engine.replicas_desired,
                config=engine.deployment_config or {},
            )
        )


class UpdateEngineDeploymentViewModel(_AdminEngineViewModel):
    """写入部署配置（可同步期望副本到主记录）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        engine_kind: EngineKindEnum,
        form: EngineDeploymentUpdateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.engine_kind = engine_kind
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        engine = await self._get_or_seed_engine(self.engine_kind)
        engine.deployment_config = _merge_config(engine.deployment_config, self.form.config)
        if self.form.replicasDesired is not None:
            engine.replicas_desired = self.form.replicasDesired
        await self.db.commit()
        await self.db.refresh(engine)
        self.operating_successfully(
            EngineDeploymentResponseData(
                engineKind=engine.engine_kind,
                replicasDesired=engine.replicas_desired,
                config=engine.deployment_config or {},
            )
        )


# 运维操作类型 → kubernetes service 调用。
def _dispatch_op(op_type: EngineOpTypeEnum, engine_key: str, form: EngineOpExecuteForm) -> kubernetes.EngineOpResult:
    if op_type == EngineOpTypeEnum.SCALE:
        return kubernetes.scale_engine(engine_key, form.replicas or 0)
    if op_type == EngineOpTypeEnum.RESTART:
        return kubernetes.trigger_restart(engine_key)
    if op_type == EngineOpTypeEnum.RELOAD:
        return kubernetes.reload_engine(engine_key)
    if op_type == EngineOpTypeEnum.DRAIN:
        return kubernetes.drain_engine(engine_key)
    if op_type == EngineOpTypeEnum.CLEAR_QUEUE:
        return kubernetes.reload_engine(engine_key)
    if op_type == EngineOpTypeEnum.REDEPLOY:
        return kubernetes.trigger_redeploy(engine_key, form.image)
    if op_type == EngineOpTypeEnum.EMERGENCY_STOP:
        return kubernetes.emergency_stop_engine(engine_key)
    if op_type == EngineOpTypeEnum.TEAR_DOWN:
        return kubernetes.tear_down_engine(engine_key)
    return kubernetes.test_connection(engine_key, "")


class ExecuteEngineOpViewModel(_AdminEngineViewModel):
    """执行引擎运维操作：调 service → 落 engine_ops → 危险操作写平台审计。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        engine_kind: EngineKindEnum,
        form: EngineOpExecuteForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.engine_kind = engine_kind
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return

        op_type = self.form.opType
        if op_type == EngineOpTypeEnum.SCALE and self.form.replicas is None:
            self.illegal_parameters("扩缩容操作需要提供目标副本数")
            return

        engine = await self._get_or_seed_engine(self.engine_kind)
        result = _dispatch_op(op_type, str(self.engine_kind), self.form)

        detail: dict[str, Any] = {}
        if self.form.replicas is not None:
            detail["replicas"] = self.form.replicas
        if self.form.image:
            detail["image"] = self.form.image

        op_status = EngineOpStatusEnum.SUCCESS if result.ok else EngineOpStatusEnum.FAILED
        op = EngineOp(
            engine_id=engine.id,
            engine_kind=self.engine_kind,
            op_type=op_type,
            status=op_status,
            message=result.message,
            operator_id=self.checker.user_id,
            detail=detail,
            error_message=None if result.ok else result.message,
        )
        # 紧急停机 / 销毁重建：同步引擎主记录状态。
        if op_type == EngineOpTypeEnum.EMERGENCY_STOP and result.ok:
            engine.status = EngineStatusEnum.STOPPED
        elif op_type == EngineOpTypeEnum.TEAR_DOWN and result.ok:
            engine.status = EngineStatusEnum.DEPLOYING

        self.db.add(op)
        await self.db.commit()
        await self.db.refresh(op)

        # 危险运维操作写平台审计日志（链式签名由 AuditLogService 保证）。
        if op_type in DANGEROUS_OP_TYPES:
            await AuditLogService.log(
                action=AuditActionEnum.EMERGENCY_STOP
                if op_type == EngineOpTypeEnum.EMERGENCY_STOP
                else AuditActionEnum.DEPLOY,
                resource="engine",
                category=AuditCategoryEnum.ENGINE,
                resource_id=str(engine.id),
                actor_type=ActorTypeEnum.ADMIN,
                actor_id=self.checker.user_id,
                actor_name=self.checker.user_name or "Admin",
                message=f"{self.engine_kind} · {result.message}",
                endpoint=str(self.request.url.path),
                method=self.request.method,
                ip_address=self.request.client.host if self.request.client else "",
                user_agent=self.request.headers.get("user-agent"),
                metadata=detail,
                status=AuditStatusEnum.SUCCESS if result.ok else AuditStatusEnum.FAILED,
                error_message=None if result.ok else result.message,
            )

        self.operating_successfully(_build_op(op))


class ListEngineOpsViewModel(_AdminEngineViewModel):
    """引擎运维流水查询（可按引擎类型筛选）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        engine_kind: EngineKindEnum | None,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.db = db
        self.engine_kind = engine_kind
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        stmt = select(EngineOp)
        if self.engine_kind is not None:
            stmt = stmt.where(EngineOp.engine_kind == self.engine_kind)
        stmt = stmt.order_by(EngineOp.created_at.desc(), EngineOp.id.desc())
        ops = (await self.db.scalars(stmt)).all()
        self.operating_successfully([_build_op(op) for op in ops])
