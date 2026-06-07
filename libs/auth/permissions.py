"""Permission checker."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import Depends, Request

from libs.auth.jwt import JWTPayload, decode_access_token
from libs.sso import generate_forbidden_exception, generate_un_auth_exception
from models.account import UserTypeEnum

__all__ = (
    "PermissionChecker",
    "get_permission_checker",
    "get_require_auth_checker",
    "require_permission",
    "require_role",
)


class PermissionChecker:
    def __init__(self) -> None:
        self.user_id: str | None = None
        self.user_type: UserTypeEnum | None = None
        self.user_name: str | None = None
        self.is_authenticated: bool = False
        self._permissions: set[str] = set()
        self._roles: list[str] = []
        self._jwt_payload: JWTPayload | None = None

    async def load_from_token(self, token: str) -> None:
        payload = decode_access_token(token)
        if payload is None:
            return

        self._jwt_payload = payload
        self.user_id = payload.user_id
        self.user_type = payload.user_type
        self._roles = payload.roles
        self.is_authenticated = True

    def require_auth(self) -> None:
        if not self.is_authenticated:
            raise generate_un_auth_exception()

    def require_user_type(self, expected_user_type: UserTypeEnum) -> None:
        self.require_auth()
        if self.user_type != expected_user_type:
            raise generate_forbidden_exception()

    def has_permission(self, permission: str) -> bool:
        return permission in self._permissions

    def has_role(self, role: str) -> bool:
        return role in self._roles


async def get_permission_checker(request: Request) -> PermissionChecker:
    checker = PermissionChecker()
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        await checker.load_from_token(token)
    return checker


def get_require_auth_checker() -> PermissionChecker:
    async def _dependency(
        checker: PermissionChecker = Depends(get_permission_checker),
    ) -> PermissionChecker:
        checker.require_auth()
        return checker

    return Depends(_dependency)


def require_permission(permission: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            checker = getattr(self, "checker", None)
            if checker is None or not checker.is_authenticated:
                raise generate_un_auth_exception()
            if not checker.has_permission(permission):
                raise generate_forbidden_exception()
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


def require_role(role_code: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            checker = getattr(self, "checker", None)
            if checker is None or not checker.is_authenticated:
                raise generate_un_auth_exception()
            if not checker.has_role(role_code):
                raise generate_forbidden_exception()
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator
