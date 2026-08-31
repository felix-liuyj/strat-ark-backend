"""ViewModel base classes."""

import secrets
from time import perf_counter
from typing import Any, Self

from fastapi import Request

from configs import get_settings
from libs.audit.context import AuditContext, clear_audit_context, set_audit_context
from libs.audit.service import AuditLogService
from libs.request_timing import record_request_timing
from libs.response import BaseResponseModel, ResponseStatusCodeEnum, get_response_message
from models.audit_log import ActorTypeEnum, AuditActionEnum

__all__ = ("BaseViewModel",)


class BaseViewModel:
    audit_action: AuditActionEnum | None = None
    audit_resource: str | None = None
    audit_enabled: bool = False

    def __init__(self, request: Request) -> None:
        self.request = request
        self.status_code: ResponseStatusCodeEnum = ResponseStatusCodeEnum.OPERATING_SUCCESSFULLY
        self.data: Any = None
        self.message: str | None = None
        self._audit_context: AuditContext | None = None

    async def __aenter__(self) -> BaseResponseModel:
        await self._init_audit_context()
        before_started = perf_counter()
        await self.before()
        record_request_timing(self.request, "viewModelBefore", (perf_counter() - before_started) * 1000)

        build_started = perf_counter()
        response = self._build_response()
        record_request_timing(self.request, "buildResponseModel", (perf_counter() - build_started) * 1000)
        return response

    async def __aexit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any) -> bool:
        if exc_type and self._audit_context:
            self._audit_context.mark_failed(str(exc_val))
        await self._save_audit_log()
        await self.after()
        return False

    async def _init_audit_context(self) -> None:
        if not self.audit_enabled:
            return

        self._audit_context = AuditContext(
            action=self.audit_action,
            resource=self.audit_resource,
            actor_type=ActorTypeEnum.SYSTEM,
            endpoint=str(self.request.url.path),
            method=self.request.method,
            ip_address=self.request.client.host if self.request.client else "",
            user_agent=self.request.headers.get("user-agent"),
        )
        set_audit_context(self._audit_context)

    async def _save_audit_log(self) -> None:
        if self._audit_context and self._audit_context.enabled:
            await AuditLogService.log_from_context(self._audit_context)
        clear_audit_context()

    async def before(self) -> None:
        return None

    async def after(self) -> None:
        return None

    def _build_response(self) -> BaseResponseModel:
        return BaseResponseModel(
            category=get_settings().APP_NO,
            code=self.status_code,
            message=self.message or get_response_message(self.status_code),
            data=self.data,
        )

    def operating_successfully(self, data: Any = None, handled: bool = False) -> Self | None:
        self.status_code = ResponseStatusCodeEnum.OPERATING_SUCCESSFULLY
        self.data = data
        return self if handled else None

    def empty_content(self, handled: bool = False) -> Self | None:
        self.status_code = ResponseStatusCodeEnum.EMPTY_CONTENT
        self.data = None
        return self if handled else None

    def nothing_changed(self, handled: bool = False) -> Self | None:
        self.status_code = ResponseStatusCodeEnum.NOTHING_CHANGED
        self.data = None
        return self if handled else None

    def operating_failed(self, message: str | None = None, handled: bool = False) -> Self | None:
        self.status_code = ResponseStatusCodeEnum.OPERATING_FAILED
        self.message = message
        self.data = None
        return self if handled else None

    def unauthorized(self, message: str | None = None, handled: bool = False) -> Self | None:
        self.status_code = ResponseStatusCodeEnum.UNAUTHORIZED
        self.message = message
        self.data = None
        return self if handled else None

    def forbidden(self, message: str | None = None, handled: bool = False) -> Self | None:
        self.status_code = ResponseStatusCodeEnum.FORBIDDEN
        self.message = message
        self.data = None
        return self if handled else None

    def not_found(self, message: str | None = None, handled: bool = False) -> Self | None:
        self.status_code = ResponseStatusCodeEnum.NOT_FOUND
        self.message = message
        self.data = None
        return self if handled else None

    def illegal_parameters(self, message: str | None = None, handled: bool = False) -> Self | None:
        self.status_code = ResponseStatusCodeEnum.ILLEGAL_PARAMETERS
        self.message = message
        self.data = None
        return self if handled else None

    def system_error(self, message: str | None = None, handled: bool = False) -> Self | None:
        self.status_code = ResponseStatusCodeEnum.SYSTEM_ERROR
        self.message = message
        self.data = None
        return self if handled else None

    def set_audit_resource_id(self, resource_id: str) -> None:
        if self._audit_context:
            self._audit_context.resource_id = resource_id

    def set_audit_changes(self, changes: dict) -> None:
        if self._audit_context:
            self._audit_context.set_changes(changes)

    def set_audit_metadata(self, key: str, value: object) -> None:
        if self._audit_context:
            self._audit_context.add_metadata(key, value)

    # -- OTP 验证码共享常量与方法 --

    OTP_CODE_LENGTH: int = 6
    OTP_EXPIRE_SECONDS: int = 300  # 5 minutes
    OTP_RATE_LIMIT_SECONDS: int = 60

    @staticmethod
    def _otp_code_key(purpose: str, email: str) -> str:
        return f"vcode:{purpose}:{email}"

    @staticmethod
    def _otp_limit_key(email: str) -> str:
        return f"vcode:limit:{email}"

    async def _verify_otp(self, email: str, code: str, purpose: str) -> bool:
        """校验验证码并在成功后从 Redis 删除，返回是否匹配。"""
        from libs import redis_cache

        key = self._otp_code_key(purpose, email)
        stored = await redis_cache.get(key)
        if stored is None or not secrets.compare_digest(stored, code):
            return False
        await redis_cache.delete(key)
        return True
