"""Client permission checker."""

from fastapi import Depends, Request

from libs.auth.jwt import JWTPayload, decode_access_token
from libs.sso import generate_forbidden_exception, generate_un_auth_exception
from models.account import UserTypeEnum

__all__ = (
    "ClientPermissionChecker",
    "get_client_permission_checker",
    "get_require_admin_checker",
    "get_require_auth_checker",
)


class ClientPermissionChecker:
    def __init__(self) -> None:
        self.user_id: str | None = None
        self.user_type: UserTypeEnum | None = None
        self.openid: str | None = None
        self.roles: list[str] = []
        self.is_authenticated: bool = False
        self._jwt_payload: JWTPayload | None = None

    async def load_from_token(self, token: str) -> None:
        payload = decode_access_token(token)
        if payload is None:
            return

        self._jwt_payload = payload
        self.user_id = payload.user_id
        self.user_type = payload.user_type
        self.openid = payload.openid
        self.roles = payload.roles
        self.is_authenticated = True

    def require_auth(self) -> None:
        if not self.is_authenticated:
            raise generate_un_auth_exception()

    def require_user_type(self, expected_user_type: UserTypeEnum) -> None:
        self.require_auth()
        if self.user_type != expected_user_type:
            raise generate_forbidden_exception()


async def get_client_permission_checker(request: Request) -> ClientPermissionChecker:
    checker = ClientPermissionChecker()
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        await checker.load_from_token(token)
    return checker


def get_require_auth_checker() -> ClientPermissionChecker:
    async def _dependency(
        checker: ClientPermissionChecker = Depends(get_client_permission_checker),
    ) -> ClientPermissionChecker:
        checker.require_auth()
        return checker

    return Depends(_dependency)


def get_require_admin_checker() -> ClientPermissionChecker:
    async def _dependency(
        checker: ClientPermissionChecker = Depends(get_client_permission_checker),
    ) -> ClientPermissionChecker:
        checker.require_user_type(UserTypeEnum.ADMIN)
        return checker

    return Depends(_dependency)
