"""OSS view models."""

from fastapi import Request

from forms.common.oss import ConfirmForm, PresignPutForm
from libs.auth.permissions import PermissionChecker
from libs.ctrl.cloud.oss import AliCloudOssBucketController
from libs.sso import generate_un_auth_exception
from libs.upload_rules import validate_object_key_directory, validate_upload_request
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

        try:
            upload = validate_upload_request(
                self.form.directory,
                self.form.filename,
                self.form.contentType,
            )
        except ValueError as exc:
            self.illegal_parameters(str(exc))
            return

        async with AliCloudOssBucketController() as oss:
            uploadUrl, fileUrl, ossPath, contentType = await oss.generate_presign_put(
                upload.filename,
                content_type=upload.content_type,
                directory=upload.directory,
            )

        self.operating_successfully(
            PresignPutResponseData(
                objectKey=ossPath,
                uploadUrl=uploadUrl,
                publicUrl=fileUrl,
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

        try:
            oss_path = validate_object_key_directory(self.form.ossPath)
        except ValueError as exc:
            self.illegal_parameters(str(exc))
            return

        async with AliCloudOssBucketController() as oss:
            await oss.confirm_object_acl(oss_path)

        self.operating_successfully(None)
