"""Audit context helpers."""

from contextvars import ContextVar
from dataclasses import dataclass, field

from models.audit_log import ActorTypeEnum, AuditActionEnum, AuditStatusEnum

__all__ = (
    "AuditContext",
    "clear_audit_context",
    "get_audit_context",
    "set_audit_context",
)

SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "token",
        "accessToken",
        "refreshToken",
        "secret",
        "apiKey",
        "privateKey",
        "sessionKey",
    }
)


@dataclass
class AuditContext:
    action: AuditActionEnum | None = None
    resource: str | None = None
    resource_id: str | None = None
    actor_type: ActorTypeEnum | None = None
    actor_id: str | None = None
    actor_name: str | None = None
    endpoint: str | None = None
    method: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    changes: dict | None = None
    metadata: dict = field(default_factory=dict)
    status: AuditStatusEnum = AuditStatusEnum.SUCCESS
    error_message: str | None = None
    enabled: bool = True

    def set_changes(self, changes: dict | None) -> None:
        self.changes = None if changes is None else self._sanitize_dict(changes)

    def add_metadata(self, key: str, value: object) -> None:
        self.metadata.update({key: value})

    def mark_failed(self, error_message: str) -> None:
        self.status = AuditStatusEnum.FAILED
        self.error_message = error_message

    def _sanitize_dict(self, data: dict) -> dict:
        result: dict = {}
        for key, value in data.items():
            if key.lower() in {field_name.lower() for field_name in SENSITIVE_FIELDS}:
                result.update({key: "***"})
            elif isinstance(value, dict):
                result.update({key: self._sanitize_dict(value)})
            else:
                result.update({key: value})
        return result


_audit_context_var: ContextVar[AuditContext | None] = ContextVar("audit_context", default=None)


def get_audit_context() -> AuditContext | None:
    return _audit_context_var.get()


def set_audit_context(context: AuditContext) -> None:
    _audit_context_var.set(context)


def clear_audit_context() -> None:
    _audit_context_var.set(None)
