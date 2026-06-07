"""Audit decorator for ViewModel methods."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from models.audit_log import AuditActionEnum

__all__ = ("audit_log",)


def audit_log(
    action: AuditActionEnum,
    resource: str,
    resource_id_param: str | None = None,
) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            if hasattr(self, "_audit_context") and self._audit_context:
                self._audit_context.action = action
                self._audit_context.resource = resource
                if resource_id_param:
                    resource_id = getattr(self, resource_id_param, None)
                    if resource_id:
                        self._audit_context.resource_id = str(resource_id)
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator
