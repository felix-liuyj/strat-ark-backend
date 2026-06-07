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
    """更新引擎部署配置。``config`` 含镜像 / 副本 / 资源 / HPA / 日志级别等。"""

    config: dict[str, Any] = Body(..., embed=True, description="部署配置")
    replicasDesired: int | None = Body(None, embed=True, description="期望副本数（同步到引擎主记录）")


class EngineOpExecuteForm(ApiFormModel):
    """执行一次引擎运维操作。"""

    opType: EngineOpTypeEnum = Body(..., embed=True, description="运维操作类型")
    replicas: int | None = Body(None, embed=True, description="扩缩容目标副本数（scale 时必填）")
    image: str | None = Body(None, embed=True, description="重建镜像标签（redeploy 可选）")
