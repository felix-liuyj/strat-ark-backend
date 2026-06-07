"""阿里云 OSS 控制器

职责：生成预签名 URL、构建 OSS 路径、删除对象、校验路径。
文件上传由前端直接向 OSS 发起，后端只接收前端回传的 oss_path。
"""

import base64
import hashlib
import hmac as hmac_module
import json
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from urllib.parse import quote, urlparse

from oss2 import Auth, Bucket
from pydantic import HttpUrl
from starlette.concurrency import run_in_threadpool

from configs import get_settings
from libs.upload_rules import (
    build_upload_object_key,
    validate_object_key_directory,
    validate_upload_request,
)

__all__ = (
    "AliCloudOssBucketController",
    "OSSPathType",
)


class OSSPathType(Enum):
    """OSS 路径类型枚举"""

    COMMON = "common"


class AliCloudOssBucketController(Bucket):
    """阿里云 OSS Bucket 控制器

    使用方式：
        async with AliCloudOssBucketController() as oss:
            presign = await oss.generate_presign(...)
    """

    _PATH_TEMPLATE = "{directory}/{id}{ext}"

    def __init__(self) -> None:
        settings = get_settings()
        self._access_key: str = (settings.ALI_OSS_ACCESS_KEY or "").strip()
        self._access_secret: str = (settings.ALI_OSS_ACCESS_SECRET or "").strip()
        self._region_id: str = self._normalize_region(settings.ALI_OSS_REGION)
        self.bucket_name: str = (settings.ALI_OSS_BUCKET_NAME or "").strip()
        self._initialized = False

    async def __aenter__(self):
        await self.login()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    @staticmethod
    def _normalize_region(region: str | None) -> str:
        """规范化 OSS 区域配置，兼容 region、endpoint 和完整 host。"""
        normalized = (region or "").strip()
        if not normalized:
            return ""

        if "://" in normalized:
            parsed = urlparse(normalized)
            normalized = parsed.hostname or ""

        normalized = normalized.strip().strip("/")
        if normalized.endswith(".aliyuncs.com"):
            normalized = normalized[: -len(".aliyuncs.com")]

        if ".oss-" in normalized:
            normalized = normalized.rsplit(".oss-", 1)[1]
        elif normalized.startswith("oss-"):
            normalized = normalized[4:]

        return normalized.strip().strip(".")

    def _ensure_region_and_bucket(self) -> None:
        missing: list[str] = []
        if not self._region_id:
            missing.append("ALI_OSS_REGION")
        if not self.bucket_name:
            missing.append("ALI_OSS_BUCKET_NAME")
        if missing:
            raise RuntimeError(f"OSS 配置不完整，请检查环境变量：{', '.join(missing)}")

    def _ensure_credentials(self) -> None:
        missing: list[str] = []
        if not self._access_key:
            missing.append("ALI_OSS_ACCESS_KEY")
        if not self._access_secret:
            missing.append("ALI_OSS_ACCESS_SECRET")
        if missing:
            raise RuntimeError(f"OSS 配置不完整，请检查环境变量：{', '.join(missing)}")

    @property
    def bucket_endpoint(self) -> str:
        self._ensure_region_and_bucket()
        return f"https://oss-{self._region_id}.aliyuncs.com"

    @property
    def access_url_prefix(self) -> str:
        self._ensure_region_and_bucket()
        return f"https://{self.bucket_name}.oss-{self._region_id}.aliyuncs.com/"

    @property
    def expected_host(self) -> str:
        self._ensure_region_and_bucket()
        return f"{self.bucket_name}.oss-{self._region_id}.aliyuncs.com"

    async def login(self) -> None:
        """初始化 OSS 客户端（幂等）"""
        if self._initialized:
            return

        self._ensure_region_and_bucket()
        self._ensure_credentials()
        Bucket.__init__(
            self,
            auth=Auth(access_key_id=self._access_key, access_key_secret=self._access_secret),
            bucket_name=self.bucket_name,
            endpoint=self.bucket_endpoint,
            region=self._region_id,
        )
        self._initialized = True

    # ==================== 路径构建 ====================

    @staticmethod
    def get_file_suffix(filename: str | None, default: str = ".jpg") -> str:
        """获取文件后缀（含点，小写）"""
        if filename:
            suffix = Path(filename).suffix
            if suffix:
                return suffix.lower()
        return default

    def build_oss_path(self, filename: str | None = None, directory: str = "common") -> str:
        """构建 OSS 路径，每次调用生成唯一路径"""
        upload = validate_upload_request(directory, filename or "upload.jpg")
        return build_upload_object_key(upload.directory, upload.extension)

    def public_url(self, oss_path: str) -> str:
        """拼接公开访问 URL"""
        return f"{self.access_url_prefix}{oss_path}"

    # ==================== 预签名生成 ====================

    async def generate_presign_put(
        self,
        filename: str,
        content_type: str = "",
        directory: str = "common",
        expire: int = 300,
    ) -> tuple[str, str, str, str]:
        """生成 PUT 预签名上传 URL

        签名中携带 Content-Type，前端直传时必须原样回填相同的 Content-Type，
        否则 OSS 会返回 403 SignatureDoesNotMatch。

        Returns:
            (upload_url, file_url, oss_path, content_type)
        """
        await self.login()
        upload = validate_upload_request(directory, filename, content_type)
        oss_path = build_upload_object_key(upload.directory, upload.extension)
        resolved_content_type = upload.content_type

        expires_ts = int(datetime.now().timestamp()) + expire
        string_to_sign = f"PUT\n\n{resolved_content_type}\n{expires_ts}\n/{self.bucket_name}/{oss_path}"
        signature = base64.b64encode(
            hmac_module.new(
                self._access_secret.encode(),
                string_to_sign.encode(),
                hashlib.sha1,
            ).digest()
        ).decode()

        encoded_path = quote(oss_path, safe="/")
        params = (
            f"OSSAccessKeyId={quote(self._access_key, safe='')}"
            f"&Expires={expires_ts}"
            f"&Signature={quote(signature, safe='')}"
        )
        upload_url = f"https://{self.bucket_name}.oss-{self._region_id}.aliyuncs.com/{encoded_path}?{params}"
        return upload_url, self.public_url(oss_path), oss_path, resolved_content_type

    @staticmethod
    def _guess_content_type(filename: str) -> str:
        """根据文件后缀推断 MIME 类型，未命中时回退为 application/octet-stream"""
        ext = Path(filename).suffix.lower()
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".pdf": "application/pdf",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".dxf": "application/dxf",
            ".zip": "application/zip",
        }.get(ext, "application/octet-stream")

    async def confirm_object_acl(self, oss_path: str) -> None:
        """将已上传的 OSS 对象设置为公开可读（兜底确认步骤）"""
        await self.login()
        validated_path = validate_object_key_directory(oss_path)
        await run_in_threadpool(self.put_object_acl, validated_path, "public-read")

    async def upload_bytes(
        self,
        data: bytes,
        filename: str,
        directory: str = "exports",
        content_type: str = "",
    ) -> tuple[str, str]:
        """服务端直传：把内存中的 bytes 上传到 OSS 并返回 (oss_path, file_url)。

        与前端 PUT 预签名上传不是同一条链路 —— 适用于由后端生成的产物
        （PDF/Excel/DXF/ZIP 等），不暴露上传凭证给前端。

        OSS 路径会用 UUID,但通过 ``Content-Disposition`` 元数据头让下载时浏览器
        使用用户可读的 ``filename``,避免跨域 ``<a download>`` 属性被忽略时
        文件名退化为 OSS 路径上的 UUID。
        """
        await self.login()
        upload = validate_upload_request(directory, filename, content_type)
        oss_path = build_upload_object_key(upload.directory, upload.extension)
        resolved_content_type = upload.content_type
        headers = {
            "Content-Type": resolved_content_type,
            "x-oss-object-acl": "public-read",
            # RFC 5987 编码,保证中文文件名跨浏览器一致;%-encoding 后浏览器自行还原。
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        }
        await run_in_threadpool(self.put_object, oss_path, data, headers=headers)
        return oss_path, self.public_url(oss_path)

    async def generate_presign_post(
        self,
        filename: str,
        expire: int = 300,
    ) -> tuple[dict, str, str]:
        """生成 POST 策略签名（兼容小程序等不支持 PUT 的客户端）

        Returns:
            (upload_fields_dict, file_url, oss_path)
        """
        await self.login()
        upload = validate_upload_request("common", filename)
        oss_path = build_upload_object_key(upload.directory, upload.extension)
        expiration = datetime.now(UTC).timestamp() + expire
        policy = {
            "expiration": datetime.fromtimestamp(expiration, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "conditions": [
                {"bucket": self.bucket_name},
                {"key": oss_path},
                ["starts-with", "$Content-Type", ""],
                {"x-oss-object-acl": "public-read"},
            ],
        }
        policy_base64 = base64.b64encode(json.dumps(policy, separators=(",", ":")).encode()).decode()
        signature = base64.b64encode(
            hmac_module.new(self._access_secret.encode(), policy_base64.encode(), hashlib.sha1).digest()
        ).decode()
        upload_data = {
            "url": f"https://{self.bucket_name}.oss-{self._region_id}.aliyuncs.com",
            "fields": {
                "key": oss_path,
                "policy": policy_base64,
                "OSSAccessKeyId": self._access_key,
                "signature": signature,
                "x-oss-object-acl": "public-read",
            },
        }
        return upload_data, self.public_url(oss_path), oss_path

    # ==================== 校验与删除 ====================

    async def object_exists(self, oss_path: str) -> bool:
        """检查 OSS 对象是否存在"""
        try:
            await self.login()
            return await run_in_threadpool(super().object_exists, key=oss_path)
        except Exception:
            return False

    def extract_oss_path(self, url: HttpUrl) -> str:
        """从 Pydantic HttpUrl 提取 OSS 路径

        Raises:
            ValueError: URL 不属于当前 Bucket
        """
        if url.host != self.expected_host:
            raise ValueError(f"URL 不属于当前 OSS Bucket: {url}")
        return validate_object_key_directory(url.path if url.path else "")

    async def validate_url(self, url: HttpUrl) -> bool:
        """校验 HttpUrl 对应的文件是否存在于当前 Bucket"""
        return await self.object_exists(self.extract_oss_path(url))

    async def delete(self, oss_path: str) -> bool:
        """删除 OSS 对象（通过路径）"""
        try:
            await self.login()
            await run_in_threadpool(self.delete_object, key=oss_path)
            return True
        except Exception:
            return False

    async def delete_by_url(self, url: str) -> bool:
        """删除 OSS 对象（通过完整 URL）"""
        if not url.startswith(self.access_url_prefix):
            return False
        return await self.delete(url[len(self.access_url_prefix) :])
