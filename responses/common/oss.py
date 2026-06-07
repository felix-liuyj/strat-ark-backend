"""OSS response models."""

from pydantic import Field

from libs.schema import ApiResponseModel

__all__ = ("PresignPutResponseData",)


class PresignPutResponseData(ApiResponseModel):
    objectKey: str = Field(..., description="OSS 对象路径")
    uploadUrl: str = Field(..., description="预签名上传地址")
    publicUrl: str = Field(..., description="上传完成后的文件访问地址")
    fileUrl: str = Field(..., description="上传完成后的文件访问地址")
    ossPath: str = Field(..., description="OSS 对象路径")
    contentType: str = Field(..., description="前端 PUT 时必须回填的 Content-Type")
