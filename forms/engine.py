"""引擎管理请求表单（管理员专属）。"""

from typing import Any

from fastapi import Body

from libs.schema import ApiFormModel
from models.engine import EngineOpTypeEnum

__all__ = (
    "EngineConnectionUpdateForm",
    "EngineDeploymentUpdateForm",
    "EngineOpExecuteForm",
)


class EngineConnectionUpdateForm(ApiFormModel):
    """更新引擎连接配置。``config`` 按引擎类型存不同字段（service URL、token、网关等）。"""

    config: dict[str, Any] = Body(..., embed=True, description="连接配置（敏感字段掩码占位则不覆盖）")


class EngineDeploymentUpdateForm(ApiFormModel):
    """更新引擎运行设置。``config`` 含日志级别 / 并发 / 模型参数等（非 k8s 编排字段）。"""

    config: dict[str, Any] = Body(..., embed=True, description="引擎运行设置")


class EngineOpExecuteForm(ApiFormModel):
    """执行一次引擎运维操作（经引擎暴露的控制 API）。"""

    opType: EngineOpTypeEnum = Body(..., embed=True, description="运维操作类型")
