"""Pydantic schema helpers for public API contracts."""

from pydantic import BaseModel, ConfigDict

__all__ = ("ApiFormModel", "ApiResponseModel")


class ApiFormModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
