from pydantic import BaseModel, Field

__all__ = ("StatusResponseData",)


class StatusResponseData(BaseModel):
    name: str = Field(..., description="服务名称")
    server: bool = Field(..., description="服务状态")
    database: bool = Field(..., description="数据库状态")
    redis: bool | None = Field(None, description="Redis 状态")
