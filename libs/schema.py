"""Pydantic schema helpers for public API contracts."""

from pydantic import BaseModel, ConfigDict

__all__ = ("ApiFormModel", "ApiResponseModel")


class ApiFormModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiResponseModel(BaseModel):
    # FastAPI 响应会序列化带默认值的字段（包括 None 与 default_factory）。
    # 在 serialization schema 中把这些固定输出键标为 required，避免客户端
    # 被 validation schema 误导为字段可能完全缺失。
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)
