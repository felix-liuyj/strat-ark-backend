"""Unified response models."""

from collections.abc import Callable
from enum import StrEnum
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

__all__ = (
    "BasePaginationResponseDataType",
    "BaseResponseModel",
    "IllegalParametersResponseModel",
    "InternalServerErrorResponseModel",
    "ResponseMessageMap",
    "ResponseStatusCodeEnum",
    "create_response",
    "get_response_message",
)


class ResponseStatusCodeEnum(StrEnum):
    OPERATING_SUCCESSFULLY = "0000"
    EMPTY_CONTENT = "0001"
    NOTHING_CHANGED = "0002"
    OPERATING_FAILED = "2000"
    ILLEGAL_PARAMETERS = "2001"
    UNAUTHORIZED = "2002"
    FORBIDDEN = "2003"
    NOT_FOUND = "2004"
    METHOD_NOT_ALLOWED = "2005"
    REQUEST_TIMEOUT = "2006"
    AUTH_ACCOUNT_NOT_FOUND = "2101"
    AUTH_PASSWORD_INCORRECT = "2102"
    AUTH_ACCOUNT_DISABLED = "2103"
    AUTH_EMAIL_ALREADY_REGISTERED = "2104"
    AUTH_VERIFICATION_CODE_INVALID = "2105"
    AUTH_VERIFICATION_CODE_RATE_LIMITED = "2106"
    SYSTEM_ERROR = "3000"


class ResponseMessageMap:
    OPERATING_SUCCESSFULLY = "成功"
    EMPTY_CONTENT = "暂无数据"
    NOTHING_CHANGED = "没有发生变更"
    OPERATING_FAILED = "操作失败"
    ILLEGAL_PARAMETERS = "提交信息有误，请检查后重试"
    UNAUTHORIZED = "登录状态已失效，请重新登录"
    FORBIDDEN = "当前账号暂无权限执行此操作"
    NOT_FOUND = "请求的数据不存在或已被删除"
    METHOD_NOT_ALLOWED = "当前请求方式不受支持"
    REQUEST_TIMEOUT = "请求超时，请稍后重试"
    AUTH_ACCOUNT_NOT_FOUND = "该邮箱尚未注册"
    AUTH_PASSWORD_INCORRECT = "密码错误，请重新输入"
    AUTH_ACCOUNT_DISABLED = "账号已被禁用"
    AUTH_EMAIL_ALREADY_REGISTERED = "该邮箱已注册"
    AUTH_VERIFICATION_CODE_INVALID = "验证码无效或已过期"
    AUTH_VERIFICATION_CODE_RATE_LIMITED = "验证码发送过于频繁，请 60 秒后重试"
    SYSTEM_ERROR = "系统繁忙，请稍后再试"


class BaseResponseModel[T](BaseModel):
    category: str = Field(..., description="Application identifier")
    code: ResponseStatusCodeEnum = Field(..., description="Business response code")
    message: str = Field(..., description="Response message")
    data: T | None = Field(None, description="Response data")


class BasePaginationResponseDataType[PGItemT](BaseModel):
    total: int = Field(..., description="Total count")
    pageNo: int = Field(..., description="Current page number")
    pageSize: int = Field(..., description="Current page size")
    hasMore: bool = Field(..., description="Whether there is a next page")
    items: list[PGItemT] = Field(..., description="Current page items")


class IllegalParametersResponseModel(BaseResponseModel[list[str]]):
    data: list[str] = Field(..., description="Validation error messages")


class InternalServerErrorResponseModel(BaseResponseModel[str]):
    data: str = Field(..., description="Internal error message")


async def create_response(
    view_model: Any,
    *args: Any,
    response_handler: Callable[[BaseResponseModel], BaseResponseModel] | None = None,
    **kwargs: Any,
) -> BaseResponseModel:
    async with view_model(*args, **kwargs) as response:
        return response_handler(response) if response_handler else response


@lru_cache
def get_response_message(status_code: ResponseStatusCodeEnum) -> str:
    message_map = ResponseMessageMap()
    return getattr(message_map, status_code.name, "Unknown")
