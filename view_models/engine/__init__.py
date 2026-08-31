"""引擎管理 view models（管理员专属）。

覆盖：引擎列表、监控聚合、连接配置读写（凭证掩码）、部署配置读写、
运维操作执行（engine_ops 记录 + 危险操作写平台审计）、运维流水查询。
"""

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from configs.catalogs import ENGINE_CATALOG
from forms.engine import (
    EngineConnectionUpdateForm,
    EngineDeploymentUpdateForm,
    EngineOpExecuteForm,
)
from libs.audit.service import AuditLogService
from libs.auth.permissions import PermissionChecker
from libs.integrations import engine_runtime
from libs.secure_config import (
    ENGINE_SENSITIVE_CONFIG_KEYS,
    decrypt_sensitive_config,
    mask_sensitive_config,
    merge_sensitive_config,
)
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

def _service_url(config: dict[str, Any] | None) -> str:
    """引擎服务探活地址：常规引擎取 serviceUrl，编排模式（freqtrade）取 orchestratorUrl。"""
    cfg = config or {}
    return str(cfg.get("serviceUrl") or cfg.get("orchestratorUrl") or "")


def _service_token(config: dict[str, Any] | None) -> str:
    cfg = config or {}
    return str(cfg.get("token") or cfg.get("restApiToken") or cfg.get("orchestratorToken") or "")


def _control_path(config: dict[str, Any] | None, key: str, fallback: str = "") -> str:
    cfg = config or {}
    return str(cfg.get(key) or fallback)


def _runtime_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return decrypt_sensitive_config(config or {}, ENGINE_SENSITIVE_CONFIG_KEYS)


def _build_engine(engine: Engine) -> EngineResponseData:
    return EngineResponseData(
        id=engine.id,
        engineKind=engine.engine_kind,
        name=engine.name,
        status=engine.status,
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
    """引擎域共享基类：统一管理员校验与显式写入创建。"""

    checker: PermissionChecker
    db: AsyncSession

    def _require_admin(self) -> bool:
        self.checker.require_auth()
        if self.checker.user_type != UserTypeEnum.ADMIN:
            self.forbidden("仅管理员可访问")
            return False
        return True

    async def _get_engine(self, engine_kind: EngineKindEnum) -> Engine:
        engine = await self.db.scalar(select(Engine).where(Engine.engine_kind == engine_kind))
        if engine is not None:
            return engine
        return self._default_engine(engine_kind, virtual=True)

    async def _get_or_create_engine(self, engine_kind: EngineKindEnum) -> Engine:
        engine = await self.db.scalar(select(Engine).where(Engine.engine_kind == engine_kind))
        if engine is not None:
            return engine
        engine = self._default_engine(engine_kind, virtual=False)
        self.db.add(engine)
        await self.db.flush()
        return engine

    @staticmethod
    def _default_engine(engine_kind: EngineKindEnum, *, virtual: bool) -> Engine:
        defaults = ENGINE_CATALOG[engine_kind]
        values: dict[str, Any] = {
            "engine_kind": engine_kind,
            "name": str(defaults["name"]),
            "status": EngineStatusEnum.STOPPED,
            "connection_config": dict(defaults["connection_config"]),
            "deployment_config": dict(defaults["deployment_config"]),
        }
        if virtual:
            values["id"] = -(list(EngineKindEnum).index(engine_kind) + 1)
        return Engine(
            **values,
        )


class ListEnginesViewModel(_AdminEngineViewModel):
    """引擎列表；缺失记录以未配置视图返回，不在 GET 路径写库。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self._require_admin():
            return
        engines = [await self._get_engine(kind) for kind in EngineKindEnum]
        self.operating_successfully([_build_engine(engine) for engine in engines])


class GetEngineMonitorViewModel(_AdminEngineViewModel):
    """引擎监控聚合（服务连接状态 + 真实端点数据）。"""

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
        engine = await self._get_engine(self.engine_kind)
        key = str(self.engine_kind)
        # 引擎经服务连接交互：运行状态由连接配置的服务地址（编排模式为编排器地址）探活派生。
        service_url = _service_url(_runtime_config(engine.connection_config))
        snapshot = engine_runtime.fetch_runtime_snapshot(key, service_url)
        deps = engine_runtime.fetch_dependencies(key)
        logs = engine_runtime.fetch_logs(key, level=self.log_level)

        self.operating_successfully(
            EngineMonitorResponseData(
                engineKind=self.engine_kind,
                runtimeStatus=snapshot.runtime_status,
                connected=snapshot.connected,
                serviceUrl=snapshot.service_url,
                latencyMs=snapshot.latency_ms,
                queueDepth=snapshot.queue_depth,
                errorRate=snapshot.error_rate,
                syncedAt=snapshot.synced_at,
                metrics=snapshot.metrics,
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
        engine = await self._get_engine(self.engine_kind)
        self.operating_successfully(
            EngineConnectionResponseData(
                engineKind=engine.engine_kind,
                config=mask_sensitive_config(engine.connection_config or {}, ENGINE_SENSITIVE_CONFIG_KEYS),
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
        engine = await self._get_or_create_engine(self.engine_kind)
        engine.connection_config = merge_sensitive_config(
            engine.connection_config or {}, self.form.config, ENGINE_SENSITIVE_CONFIG_KEYS
        )
        await self.db.commit()
        await self.db.refresh(engine)
        self.operating_successfully(
            EngineConnectionResponseData(
                engineKind=engine.engine_kind,
                config=mask_sensitive_config(engine.connection_config or {}, ENGINE_SENSITIVE_CONFIG_KEYS),
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
        engine = await self._get_engine(self.engine_kind)
        self.operating_successfully(
            EngineDeploymentResponseData(
                engineKind=engine.engine_kind,
                config=engine.deployment_config or {},
            )
        )


class UpdateEngineDeploymentViewModel(_AdminEngineViewModel):
    """写入引擎运行设置（日志级别 / 并发 / 模型参数等）。"""

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
        engine = await self._get_or_create_engine(self.engine_kind)
        engine.deployment_config = dict(engine.deployment_config or {}) | self.form.config
        await self.db.commit()
        await self.db.refresh(engine)
        self.operating_successfully(
            EngineDeploymentResponseData(
                engineKind=engine.engine_kind,
                config=engine.deployment_config or {},
            )
        )


# 运维操作类型 → 引擎服务连接调用（经引擎暴露的控制 API；test_connection 探 serviceUrl）。
def _dispatch_op(
    op_type: EngineOpTypeEnum,
    engine_key: str,
    config: dict[str, Any],
) -> engine_runtime.EngineOpResult:
    service_url = _service_url(config)
    token = _service_token(config)
    if op_type == EngineOpTypeEnum.RESTART:
        return engine_runtime.trigger_restart(engine_key, service_url, token, _control_path(config, "restartPath"))
    if op_type == EngineOpTypeEnum.RELOAD:
        path = _control_path(config, "reloadPath", "/api/v1/reload_config")
        return engine_runtime.reload_engine(engine_key, service_url, token, path)
    if op_type == EngineOpTypeEnum.DRAIN:
        return engine_runtime.drain_engine(engine_key, service_url, token, _control_path(config, "drainPath"))
    if op_type == EngineOpTypeEnum.CLEAR_QUEUE:
        path = _control_path(config, "clearQueuePath")
        return engine_runtime.clear_queue_engine(engine_key, service_url, token, path)
    if op_type == EngineOpTypeEnum.EMERGENCY_STOP:
        path = _control_path(config, "stopPath", "/api/v1/stop")
        return engine_runtime.emergency_stop_engine(engine_key, service_url, token, path)
    if op_type == EngineOpTypeEnum.TEAR_DOWN:
        return engine_runtime.tear_down_engine(engine_key, service_url, token, _control_path(config, "tearDownPath"))
    return engine_runtime.test_connection(engine_key, service_url)


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
        engine = await self._get_or_create_engine(self.engine_kind)
        runtime_config = _runtime_config(engine.connection_config)
        service_url = _service_url(runtime_config)
        result = _dispatch_op(op_type, str(self.engine_kind), runtime_config)

        detail: dict[str, Any] = {
            "serviceUrl": service_url,
            "operation": result.operation,
            "runtimeStatus": result.runtime_status,
            "executedAt": result.executed_at.isoformat(),
        }

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
