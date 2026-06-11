"""设置域响应数据模型。

覆盖前端 SettingsPage 各分组：General / LLM / Prompt 模板 / Appearance / Data。
LLM 的 API Key 经掩码后返回（仅展示尾部若干位）。
"""

from typing import Any

from pydantic import Field

from libs.schema import ApiResponseModel
from models.settings import SystemConfigGroupEnum

__all__ = (
    "ConfigGroupResponseData",
    "DataActionResponseData",
    "LlmConnectionTestResponseData",
    "PromptTemplateResponseData",
    "SettingsOverviewResponseData",
)


class ConfigGroupResponseData(ApiResponseModel):
    """单个配置分组的全部配置项。

    items 为 key -> value 字典；LLM 分组中 apiKey 已掩码，未配置时返回空字符串。
    """

    group: SystemConfigGroupEnum = Field(..., description="配置分组")
    items: dict[str, Any] = Field(..., description="配置项 key -> value 字典")


class PromptTemplateResponseData(ApiResponseModel):
    """Prompt 模板项（与前端 Prompt 模板列表对齐）。"""

    id: str = Field(..., description="模板 id")
    name: str = Field(..., description="模板名称")
    description: str = Field(..., description="模板说明")
    content: str = Field(..., description="模板正文")
    enabled: bool = Field(..., description="是否启用")


class SettingsOverviewResponseData(ApiResponseModel):
    """设置总览：四个标量分组 + Prompt 模板列表，供页面一次加载。"""

    general: dict[str, Any] = Field(..., description="General 分组配置")
    llm: dict[str, Any] = Field(..., description="LLM 分组配置（apiKey 已掩码）")
    appearance: dict[str, Any] = Field(..., description="Appearance 分组配置")
    data: dict[str, Any] = Field(..., description="Data 分组配置")
    promptTemplates: list[PromptTemplateResponseData] = Field(..., description="Prompt 模板列表")


class DataActionResponseData(ApiResponseModel):
    """数据导出 / 清除操作结果。"""

    action: str = Field(..., description="操作类型：export / clear")
    target: str = Field(..., description="操作对象")
    message: str = Field(..., description="结果说明")
    downloadUrl: str | None = Field(None, description="导出文件下载地址")


class LlmConnectionTestResponseData(ApiResponseModel):
    """LLM 模型网关连接测试结果。"""

    ok: bool = Field(..., description="连接是否成功")
    provider: str = Field(..., description="模型服务商")
    model: str = Field(..., description="模型名称")
    latencyMs: int = Field(..., description="测试延迟，单位毫秒")
    message: str = Field(..., description="结果说明")
