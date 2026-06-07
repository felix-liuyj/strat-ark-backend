"""审计日志服务：持久化 + 链式签名。"""

import hashlib
import json

from pydantic import BaseModel
from sqlalchemy import select

from libs.audit.context import AuditContext
from libs.ctrl.db.sqlalchemy import new_async_session
from libs.logger import logger
from models.audit_log import ActorTypeEnum, AuditActionEnum, AuditCategoryEnum, AuditLog, AuditStatusEnum

__all__ = ("AuditLogService",)


class AuditLogService:
    @staticmethod
    def _compute_signature(prev: str | None, payload: dict) -> str:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(f"{prev or ''}|{body}".encode()).hexdigest()

    @staticmethod
    async def log(
        action: AuditActionEnum,
        resource: str,
        *,
        category: AuditCategoryEnum = AuditCategoryEnum.SYSTEM,
        resource_id: str | None = None,
        actor_type: ActorTypeEnum = ActorTypeEnum.SYSTEM,
        actor_id: str | None = None,
        actor_name: str | None = None,
        message: str = "",
        endpoint: str = "",
        method: str = "",
        ip_address: str = "",
        user_agent: str | None = None,
        changes: dict | None = None,
        metadata: dict | None = None,
        status: AuditStatusEnum = AuditStatusEnum.SUCCESS,
        error_message: str | None = None,
    ) -> None:
        details: dict = {}
        if changes:
            details["changes"] = changes
        if metadata:
            details.update(metadata)
        try:
            async with new_async_session() as db:
                prev = (await db.scalars(select(AuditLog.signature).order_by(AuditLog.id.desc()).limit(1))).first()
                row = AuditLog(
                    actor=actor_name or "System",
                    actor_id=actor_id,
                    actor_type=str(actor_type),
                    action=str(action),
                    category=str(category),
                    resource=resource,
                    resource_id=resource_id,
                    message=message,
                    details=details,
                    status=str(status),
                    error_message=error_message,
                    endpoint=endpoint or None,
                    method=method or None,
                    ip_address=ip_address or None,
                    user_agent=user_agent,
                    prev_signature=prev,
                )
                row.signature = AuditLogService._compute_signature(
                    prev,
                    {
                        "actor": row.actor,
                        "actor_type": row.actor_type,
                        "action": row.action,
                        "category": row.category,
                        "resource": row.resource,
                        "resource_id": row.resource_id,
                        "message": row.message,
                        "status": row.status,
                        "details": details,
                    },
                )
                db.add(row)
                await db.commit()
        except Exception as exc:  # 审计失败绝不影响主流程
            logger.error(f"Audit log persist failed: {exc}")

    @staticmethod
    async def log_from_context(context: AuditContext) -> None:
        await AuditLogService.log(
            action=context.action or AuditActionEnum.READ,
            resource=context.resource or "",
            resource_id=context.resource_id,
            actor_type=context.actor_type or ActorTypeEnum.SYSTEM,
            actor_id=context.actor_id,
            actor_name=context.actor_name,
            endpoint=context.endpoint or "",
            method=context.method or "",
            ip_address=context.ip_address or "",
            user_agent=context.user_agent,
            changes=context.changes,
            metadata=context.metadata,
            status=context.status,
            error_message=context.error_message,
        )

    @staticmethod
    def compute_changes(old_model: BaseModel | dict, new_model: BaseModel | dict) -> dict:
        def _to_dict(value: BaseModel | dict) -> dict:
            if isinstance(value, BaseModel):
                return {field: getattr(value, field) for field in type(value).model_fields}
            return value

        changes: dict = {}
        old_data = _to_dict(old_model)
        new_data = _to_dict(new_model)
        for field_name in set(old_data.keys()) | set(new_data.keys()):
            old_value = old_data.get(field_name)
            new_value = new_data.get(field_name)
            if old_value != new_value:
                changes[field_name] = {"old": old_value, "new": new_value}
        return changes
