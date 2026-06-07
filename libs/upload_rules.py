"""OSS 上传路径与文件类型白名单。"""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

__all__ = (
    "UploadRequest",
    "build_upload_object_key",
    "list_upload_directories",
    "validate_object_key_directory",
    "validate_oss_url",
    "validate_upload_request",
)


_RULES: dict[str, frozenset[str]] = {
    "avatars": frozenset({"jpg", "jpeg", "png", "webp"}),
    "banners": frozenset({"jpg", "jpeg", "png", "webp"}),
    "common": frozenset({"jpg", "jpeg", "png", "webp", "pdf"}),
    "exports": frozenset({"csv", "dxf", "json", "pdf", "xlsx", "zip"}),
    "materials": frozenset({"doc", "docx", "pdf"}),
    "reports": frozenset({"csv", "json", "pdf", "xlsx"}),
    "strategies": frozenset({"py", "txt", "zip"}),
}

_CONTENT_TYPES: dict[str, str] = {
    "csv": "text/csv",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "dxf": "application/dxf",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "json": "application/json",
    "pdf": "application/pdf",
    "png": "image/png",
    "py": "text/x-python",
    "txt": "text/plain",
    "webp": "image/webp",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}

_CONTENT_TYPE_ALIASES: dict[str, frozenset[str]] = {
    "csv": frozenset({"application/csv", "text/plain"}),
    "dxf": frozenset({"application/octet-stream", "image/vnd.dxf"}),
    "json": frozenset({"text/json"}),
    "py": frozenset({"application/octet-stream", "text/plain"}),
    "txt": frozenset({"application/octet-stream"}),
    "zip": frozenset({"application/octet-stream", "application/x-zip-compressed"}),
}


@dataclass(frozen=True, slots=True)
class UploadRequest:
    directory: str
    filename: str
    extension: str
    content_type: str


def list_upload_directories() -> tuple[str, ...]:
    return tuple(sorted(_RULES))


def _normalize_directory(directory: str) -> str:
    normalized = directory.strip().strip("/").replace("\\", "/")
    if "/" in normalized or not normalized:
        raise ValueError("OSS 上传目录不合法")
    if normalized not in _RULES:
        raise ValueError(f"OSS 上传目录不在白名单：{normalized}")
    return normalized


def _extension_from_filename(filename: str) -> str:
    extension = Path(filename.strip()).suffix.lower().lstrip(".")
    if not filename.strip() or not extension:
        raise ValueError("上传文件名必须包含扩展名")
    return extension


def _check_extension(directory: str, extension: str) -> None:
    if extension not in _RULES[directory]:
        allowed = ", ".join(sorted(_RULES[directory]))
        raise ValueError(f"目录 {directory} 不允许上传 .{extension} 文件，可用扩展名：{allowed}")


def _normalize_content_type(extension: str, content_type: str) -> str:
    incoming = content_type.strip().lower()
    expected = _CONTENT_TYPES.get(extension, "application/octet-stream")
    if not incoming or incoming == "application/octet-stream":
        return expected
    if incoming == expected or incoming in _CONTENT_TYPE_ALIASES.get(extension, frozenset()):
        return incoming
    raise ValueError(f".{extension} 文件的 Content-Type 不匹配：{incoming}")


def validate_upload_request(directory: str, filename: str, content_type: str = "") -> UploadRequest:
    normalized_directory = _normalize_directory(directory)
    extension = _extension_from_filename(filename)
    _check_extension(normalized_directory, extension)
    return UploadRequest(
        directory=normalized_directory,
        filename=filename.strip(),
        extension=extension,
        content_type=_normalize_content_type(extension, content_type),
    )


def build_upload_object_key(directory: str, extension: str) -> str:
    normalized_directory = _normalize_directory(directory)
    _check_extension(normalized_directory, extension)
    return f"{normalized_directory}/{uuid4().hex}.{extension}"


def _assert_clean_object_key(object_key: str) -> list[str]:
    key = object_key.strip().lstrip("/")
    parts = key.split("/")
    if len(parts) != 2 or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("OSS 对象路径不合法")
    return parts


def validate_object_key_directory(object_key: str) -> str:
    directory, filename = _assert_clean_object_key(object_key)
    normalized_directory = _normalize_directory(directory)
    extension = _extension_from_filename(filename)
    _check_extension(normalized_directory, extension)
    return f"{normalized_directory}/{filename}"


def validate_oss_url(url: str, expected_host: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc != expected_host:
        raise ValueError("OSS URL 不属于当前 Bucket")
    return validate_object_key_directory(parsed.path)
