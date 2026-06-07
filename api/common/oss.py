"""OSS API."""

from fastapi import APIRouter, Depends, Request

from forms.common.oss import ConfirmForm, PresignPutForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.response import BaseResponseModel, create_response
from responses.common.oss import PresignPutResponseData
from view_models.common.oss import ConfirmViewModel, CreatePresignPutViewModel

__all__ = ("router",)

router = APIRouter(prefix="/oss")


@router.post(
    "/presign",
    response_model=BaseResponseModel[PresignPutResponseData],
    summary="申请 OSS PUT 预签名",
    description="前端通过该接口获取预签名 URL，再直接将文件上传至 OSS（需登录）。",
    tags=["通用 Common/OSS"],
)
async def presign(
    request: Request,
    form: PresignPutForm,
    checker: PermissionChecker = Depends(get_permission_checker),
) -> BaseResponseModel:
    return await create_response(CreatePresignPutViewModel, request, form=form, checker=checker)


@router.post(
    "/confirm",
    response_model=BaseResponseModel[None],
    summary="确认上传并设置对象 ACL",
    description="上传完成后调用，后端将 OSS 对象显式设置为 public-read（需登录）。",
    tags=["通用 Common/OSS"],
)
async def confirm(
    request: Request,
    form: ConfirmForm,
    checker: PermissionChecker = Depends(get_permission_checker),
) -> BaseResponseModel:
    return await create_response(ConfirmViewModel, request, form=form, checker=checker)
