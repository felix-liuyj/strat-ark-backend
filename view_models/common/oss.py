"""OSS view models."""

from fastapi import Request

from forms.common.oss import ConfirmForm, PresignPutForm
from libs.auth.permissions import PermissionChecker
from libs.ctrl.cloud.oss import AliCloudOssBucketController
from libs.sso import generate_un_auth_exception
from responses.common.oss import PresignPutResponseData
from view_models.common.base import BaseViewModel

__all__ = ("ConfirmViewModel", "CreatePresignPutViewModel")


class CreatePresignPutViewModel(BaseViewModel):
    def __init__(
        self,
        request: Request,
        *,
        form: PresignPutForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self.checker.is_authenticated:
            raise generate_un_auth_exception()

        async with AliCloudOssBucketController() as oss:
            uploadUrl, fileUrl, ossPath, contentType = await oss.generate_presign_put(
                self.form.filename,
                content_type=self.form.contentType,
                directory=self.form.directory,
            )

        self.operating_successfully(
            PresignPutResponseData(
                uploadUrl=uploadUrl,
                fileUrl=fileUrl,
                ossPath=ossPath,
                contentType=contentType,
            )
        )


class ConfirmViewModel(BaseViewModel):
    def __init__(
        self,
        request: Request,
        *,
        form: ConfirmForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker

    async def before(self) -> None:
        await super().before()
        if not self.checker.is_authenticated:
            raise generate_un_auth_exception()

        async with AliCloudOssBucketController() as oss:
            await oss.confirm_object_acl(self.form.ossPath)

        self.operating_successfully(None)
