"""SSO / auth helper utilities."""

from fastapi import HTTPException
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

__all__ = (
    "AUTH_FORBIDDEN_MESSAGE",
    "AUTH_INVALID_MESSAGE",
    "generate_forbidden_exception",
    "generate_un_auth_exception",
)

AUTH_INVALID_MESSAGE = "登录状态已失效，请重新登录"
AUTH_FORBIDDEN_MESSAGE = "当前账号暂无权限执行此操作"


def generate_un_auth_exception(detail: str = AUTH_INVALID_MESSAGE) -> HTTPException:
    return HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=detail)


def generate_forbidden_exception(detail: str = AUTH_FORBIDDEN_MESSAGE) -> HTTPException:
    return HTTPException(status_code=HTTP_403_FORBIDDEN, detail=detail)
