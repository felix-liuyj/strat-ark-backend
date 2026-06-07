"""OSS forms."""

from fastapi import Body

from libs.schema import ApiFormModel

__all__ = ("ConfirmForm", "PresignPutForm")


class PresignPutForm(ApiFormModel):
    filename: str = Body(..., embed=True, description="待上传文件名")
    contentType: str = Body("", embed=True, description="文件 MIME 类型，空则按后缀自动推断")
    directory: str = Body(
        "common",
        embed=True,
        description="OSS 存储目录：avatars / banners / common / exports / materials / reports / strategies",
    )


class ConfirmForm(ApiFormModel):
    ossPath: str = Body(..., embed=True, description="OSS 对象路径")
