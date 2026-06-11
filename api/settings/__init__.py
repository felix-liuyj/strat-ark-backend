"""设置域 API 路由：配置总览 / 分组更新 / Prompt 模板 CRUD / 数据导出清除。"""

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.settings import (
    ClearDataForm,
    ExportDataForm,
    LlmConnectionTestForm,
    PromptTemplateForm,
    UpdateConfigGroupForm,
)
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.settings import (
    ConfigGroupResponseData,
    DataActionResponseData,
    LlmConnectionTestResponseData,
    PromptTemplateResponseData,
    SettingsOverviewResponseData,
)
from view_models.settings import (
    ClearDataViewModel,
    CreatePromptTemplateViewModel,
    DeletePromptTemplateViewModel,
    ExportDataViewModel,
    GetSettingsOverviewViewModel,
    TestLlmConnectionViewModel,
    UpdateConfigGroupViewModel,
    UpdatePromptTemplateViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/settings",
    response_model=BaseResponseModel[SettingsOverviewResponseData],
    summary="获取设置总览",
    description="一次性返回 General / LLM / Appearance / Data 四个分组配置与 Prompt 模板列表（LLM API Key 已掩码）。",
    tags=["StratArk/系统设置"],
)
async def get_settings_overview(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetSettingsOverviewViewModel, request, db, checker=checker)


@router.put(
    "/settings/group",
    response_model=BaseResponseModel[ConfigGroupResponseData],
    summary="更新配置分组",
    description="整组 upsert 指定分组（general / llm / appearance / data）的配置项；Prompt 模板请用模板专用接口。",
    tags=["StratArk/系统设置"],
)
async def update_config_group(
    request: Request,
    form: UpdateConfigGroupForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(UpdateConfigGroupViewModel, request, db, checker=checker, form=form)


@router.post(
    "/settings/llm/test",
    response_model=BaseResponseModel[LlmConnectionTestResponseData],
    summary="测试 LLM 网关连接",
    description="使用提交的 provider / endpoint / apiKey 测试模型网关；apiKey 留空或为掩码时复用已保存配置。",
    tags=["StratArk/系统设置"],
)
async def test_llm_connection(
    request: Request,
    form: LlmConnectionTestForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(TestLlmConnectionViewModel, request, db, checker=checker, form=form)


@router.post(
    "/settings/prompt-templates",
    response_model=BaseResponseModel[PromptTemplateResponseData],
    summary="新建 Prompt 模板",
    description="创建一个 Prompt 模板；若设为启用，会自动停用其它启用模板（单一启用）。",
    tags=["StratArk/系统设置"],
)
async def create_prompt_template(
    request: Request,
    form: PromptTemplateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreatePromptTemplateViewModel, request, db, checker=checker, form=form)


@router.put(
    "/settings/prompt-templates/{template_id}",
    response_model=BaseResponseModel[PromptTemplateResponseData],
    summary="更新 Prompt 模板",
    description="按模板 id 更新名称 / 说明 / 正文 / 启用态；启用时自动停用其它模板。",
    tags=["StratArk/系统设置"],
)
async def update_prompt_template(
    request: Request,
    form: PromptTemplateForm,
    template_id: str = Path(..., description="Prompt 模板 id"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        UpdatePromptTemplateViewModel, request, db, template_id=template_id, checker=checker, form=form
    )


@router.delete(
    "/settings/prompt-templates/{template_id}",
    response_model=BaseResponseModel[None],
    summary="删除 Prompt 模板",
    description="按模板 id 删除一个 Prompt 模板。",
    tags=["StratArk/系统设置"],
)
async def delete_prompt_template(
    request: Request,
    template_id: str = Path(..., description="Prompt 模板 id"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(DeletePromptTemplateViewModel, request, db, template_id=template_id, checker=checker)


@router.post(
    "/settings/data/export",
    response_model=BaseResponseModel[DataActionResponseData],
    summary="导出数据",
    description="导出当前用户交易与回测数据，返回可直接下载的文件地址。",
    tags=["StratArk/系统设置"],
)
async def export_data_endpoint(
    request: Request,
    form: ExportDataForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ExportDataViewModel, request, db, checker=checker, form=form)


@router.post(
    "/settings/data/clear",
    response_model=BaseResponseModel[DataActionResponseData],
    summary="清除数据",
    description="清除行情缓存或当前用户全部 Bot 与策略相关数据，危险操作由前端二次确认。",
    tags=["StratArk/系统设置"],
)
async def clear_data_endpoint(
    request: Request,
    form: ClearDataForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ClearDataViewModel, request, db, checker=checker, form=form)
