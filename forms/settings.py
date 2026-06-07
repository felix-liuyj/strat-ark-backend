"""设置域请求表单。"""

from typing import Any

from fastapi import Body

from libs.schema import ApiFormModel
from models.settings import SystemConfigGroupEnum

__all__ = (
    "ClearDataForm",
    "ExportDataForm",
    "LlmConnectionTestForm",
    "PromptTemplateForm",
    "UpdateConfigGroupForm",
)


class UpdateConfigGroupForm(ApiFormModel):
    """更新某分组下的一批配置项（整组 upsert）。

    items 为 key -> value 的字典；value 可为标量 / 对象 / 列表。
    适用于 General / LLM / Appearance / Data 的批量保存（Prompt 用专用表单）。
    """

    group: SystemConfigGroupEnum = Body(..., embed=True, description="配置分组")
    items: dict[str, Any] = Body(..., embed=True, description="配置项 key -> value 字典")


class PromptTemplateForm(ApiFormModel):
    """Prompt 模板创建 / 更新表单。

    创建时不传 id（由后端生成）；更新时通过路径参数定位，name/content/enabled 覆盖。
    """

    name: str = Body(..., embed=True, description="模板名称")
    description: str = Body("", embed=True, description="模板说明")
    content: str = Body("", embed=True, description="Prompt 模板正文")
    enabled: bool = Body(False, embed=True, description="是否启用（启用态用于实际分析）")


class ExportDataForm(ApiFormModel):
    """数据导出请求。"""

    fmt: str = Body("csv", embed=True, description="导出格式：csv / json")
    scope: str = Body("all", embed=True, description="导出范围：all / trades / backtests")


class ClearDataForm(ApiFormModel):
    """数据清除请求（行情缓存 / Bot 与策略等）。"""

    target: str = Body(..., embed=True, description="清除目标：market_cache / bots_strategies")


class LlmConnectionTestForm(ApiFormModel):
    """LLM 模型网关连接测试请求。"""

    provider: str = Body(..., embed=True, description="模型服务商")
    model: str = Body(..., embed=True, description="模型名称")
    endpoint: str = Body(..., embed=True, description="模型网关地址")
    apiKey: str = Body("", embed=True, description="API Key；留空或掩码时使用已保存配置")
