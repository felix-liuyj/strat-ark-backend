"""Application exception handlers."""

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from configs import get_settings
from libs.response import ResponseStatusCodeEnum, get_response_message

__all__ = (
    "AppServiceException",
    "ForbiddenException",
    "IllegalParametersException",
    "NotFoundException",
    "custom_app_service_exception_handler",
    "custom_auth_forbidden_exception_handler",
    "custom_internal_server_exception_handler",
    "custom_un_auth_exception_handler",
    "custom_validation_exception_handler",
)


class AppServiceException(Exception):
    def __init__(self, message: str, code: ResponseStatusCodeEnum = ResponseStatusCodeEnum.OPERATING_FAILED) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ForbiddenException(AppServiceException):
    def __init__(self, message: str = "无权访问此资源") -> None:
        super().__init__(message, code=ResponseStatusCodeEnum.FORBIDDEN)


class IllegalParametersException(AppServiceException):
    def __init__(self, message: str = "提交信息有误，请检查后重试") -> None:
        super().__init__(message, code=ResponseStatusCodeEnum.ILLEGAL_PARAMETERS)


class NotFoundException(AppServiceException):
    def __init__(self, message: str = "请求的数据不存在或已被删除") -> None:
        super().__init__(message, code=ResponseStatusCodeEnum.NOT_FOUND)


async def custom_un_auth_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "category": get_settings().APP_NO,
            "code": ResponseStatusCodeEnum.UNAUTHORIZED.value,
            "message": str(exc.detail) or "登录状态已失效，请重新登录",
            "data": None,
        },
    )


async def custom_auth_forbidden_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "category": get_settings().APP_NO,
            "code": ResponseStatusCodeEnum.FORBIDDEN.value,
            "message": str(exc.detail) or "当前账号暂无权限执行此操作",
            "data": None,
        },
    )


async def custom_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "category": get_settings().APP_NO,
            "code": ResponseStatusCodeEnum.ILLEGAL_PARAMETERS.value,
            "message": get_response_message(ResponseStatusCodeEnum.ILLEGAL_PARAMETERS),
            "data": [
                f"{' -> '.join(map(str, error.get('loc', [])))}: {error.get('msg', 'invalid value')}"
                for error in exc.errors()
            ],
        },
    )


async def custom_app_service_exception_handler(request: Request, exc: AppServiceException) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "category": get_settings().APP_NO,
            "code": exc.code.value,
            "message": exc.message,
            "data": None,
        },
    )


async def custom_internal_server_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "category": get_settings().APP_NO,
            "code": ResponseStatusCodeEnum.SYSTEM_ERROR.value,
            "message": "系统繁忙，请稍后再试",
            "data": None,
        },
    )
