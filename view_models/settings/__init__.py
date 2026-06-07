"""设置域 ViewModel：系统配置读写 + Prompt 模板 CRUD + 数据导出 / 清除。

配置按 用户 + 分组 + key 存于 ``system_configs``；首次读取惰性种入默认值（与前端
SettingsPage 默认展示一致）。LLM API Key 入库存明文、响应层掩码返回。
"""

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.settings import (
    ClearDataForm,
    ExportDataForm,
    PromptTemplateForm,
    UpdateConfigGroupForm,
)
from libs.auth.permissions import PermissionChecker
from libs.integrations.data_ops import clear_data, export_data
from models.audit_log import ActorTypeEnum, AuditActionEnum, AuditCategoryEnum
from models.settings import SystemConfig, SystemConfigGroupEnum
from responses.settings import (
    ConfigGroupResponseData,
    DataActionResponseData,
    PromptTemplateResponseData,
    SettingsOverviewResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = (
    "ClearDataViewModel",
    "CreatePromptTemplateViewModel",
    "DeletePromptTemplateViewModel",
    "ExportDataViewModel",
    "GetSettingsOverviewViewModel",
    "UpdateConfigGroupViewModel",
    "UpdatePromptTemplateViewModel",
)

# 敏感字段集合：响应层掩码、不回明文。
_SECRET_KEYS: frozenset[str] = frozenset({"apiKey"})

# 各分组默认配置种子（与前端 SettingsPage 默认值对齐）。
_GENERAL_DEFAULTS: dict[str, Any] = {
    "language": "zh-CN",
    "timezone": "UTC+8",
    "defaultExchange": "Binance Futures",
    "quoteCurrency": "USDT",
    "confirmLiveActions": True,
    "defaultDryRun": True,
    "showRiskBanner": True,
}
_LLM_DEFAULTS: dict[str, Any] = {
    "provider": "Anthropic",
    "model": "claude-sonnet",
    "temperature": "0.3",
    "maxTokens": "4096",
    "endpoint": "https://api.anthropic.com",
    "apiKey": "sk-ant-0000000000007f3a",
    "monthlyTokenQuota": 10_000_000,
    "monthlyAnalysisQuota": 300,
}
_APPEARANCE_DEFAULTS: dict[str, Any] = {
    "colorMode": "dark",
    "accent": "#5EEAD4",
    "density": "standard",
    "reduceMotion": False,
}
_DATA_DEFAULTS: dict[str, Any] = {
    "auditRetention": "1y",
}

_GROUP_DEFAULTS: dict[SystemConfigGroupEnum, dict[str, Any]] = {
    SystemConfigGroupEnum.GENERAL: _GENERAL_DEFAULTS,
    SystemConfigGroupEnum.LLM: _LLM_DEFAULTS,
    SystemConfigGroupEnum.APPEARANCE: _APPEARANCE_DEFAULTS,
    SystemConfigGroupEnum.DATA: _DATA_DEFAULTS,
}

# Prompt 模板默认种子（与前端 Prompt 模板列表对齐）。
_PROMPT_SEED: list[dict[str, Any]] = [
    {
        "name": "综合市场分析 · Full Analysis",
        "description": "8 个 Agent 协作 · 默认模板",
        "content": "对给定标的进行多智能体综合分析，输出方向、置信度与理由。",
        "enabled": True,
    },
    {
        "name": "技术面分析 · Technical Only",
        "description": "仅技术指标与价格结构",
        "content": "仅基于技术指标与价格结构给出交易判断。",
        "enabled": False,
    },
    {
        "name": "回测复盘 · Backtest Review",
        "description": "解释回测结果与改进建议",
        "content": "解读回测指标，指出问题并给出改进建议。",
        "enabled": False,
    },
    {
        "name": "风险摘要 · Risk Summary",
        "description": "生成 Bot 风险评估摘要",
        "content": "基于持仓与风控规则生成 Bot 风险评估摘要。",
        "enabled": False,
    },
]


def _mask_secret(value: Any) -> str:
    """掩码敏感字符串：保留前缀与尾 4 位，中间以圆点替代。"""
    text = str(value or "")
    if len(text) <= 8:
        return "••••"
    head = text[:6]
    tail = text[-4:]
    return f"{head}••••{tail}"


def _mask_group(group: SystemConfigGroupEnum, items: dict[str, Any]) -> dict[str, Any]:
    if group != SystemConfigGroupEnum.LLM:
        return items
    return {k: (_mask_secret(v) if k in _SECRET_KEYS else v) for k, v in items.items()}


async def _load_group(
    db: AsyncSession, user_id: int, group: SystemConfigGroupEnum
) -> dict[str, Any]:
    """读取某标量分组配置；缺失项用默认值补齐并持久化（惰性种入）。"""
    rows = (
        await db.scalars(
            select(SystemConfig).where(
                SystemConfig.user_id == user_id,
                SystemConfig.group == group,
            )
        )
    ).all()
    stored = {row.key: row.value for row in rows}
    defaults = _GROUP_DEFAULTS.get(group, {})

    missing = {k: v for k, v in defaults.items() if k not in stored}
    if missing:
        for key, value in missing.items():
            db.add(SystemConfig(user_id=user_id, group=group, key=key, value=value))
        await db.commit()
        stored |= missing
    return stored


async def _load_prompt_templates(db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    """读取 Prompt 模板（group=prompt 多行）；为空时种入默认模板。"""
    rows = (
        await db.scalars(
            select(SystemConfig)
            .where(
                SystemConfig.user_id == user_id,
                SystemConfig.group == SystemConfigGroupEnum.PROMPT,
            )
            .order_by(SystemConfig.id.asc())
        )
    ).all()
    if not rows:
        for seed in _PROMPT_SEED:
            tpl_id = uuid.uuid4().hex
            db.add(
                SystemConfig(
                    user_id=user_id,
                    group=SystemConfigGroupEnum.PROMPT,
                    key=tpl_id,
                    value={"id": tpl_id, **seed},
                )
            )
        await db.commit()
        rows = (
            await db.scalars(
                select(SystemConfig)
                .where(
                    SystemConfig.user_id == user_id,
                    SystemConfig.group == SystemConfigGroupEnum.PROMPT,
                )
                .order_by(SystemConfig.id.asc())
            )
        ).all()
    return [dict(row.value) for row in rows]


def _build_template_response(value: dict[str, Any]) -> PromptTemplateResponseData:
    return PromptTemplateResponseData(
        id=str(value.get("id", "")),
        name=str(value.get("name", "")),
        description=str(value.get("description", "")),
        content=str(value.get("content", "")),
        enabled=bool(value.get("enabled", False)),
    )


class GetSettingsOverviewViewModel(BaseViewModel):
    """设置总览：四个标量分组 + Prompt 模板，一次性返回。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        general = await _load_group(self.db, user_id, SystemConfigGroupEnum.GENERAL)
        llm = await _load_group(self.db, user_id, SystemConfigGroupEnum.LLM)
        appearance = await _load_group(self.db, user_id, SystemConfigGroupEnum.APPEARANCE)
        data = await _load_group(self.db, user_id, SystemConfigGroupEnum.DATA)
        templates = await _load_prompt_templates(self.db, user_id)

        self.operating_successfully(
            SettingsOverviewResponseData(
                general=general,
                llm=_mask_group(SystemConfigGroupEnum.LLM, llm),
                appearance=appearance,
                data=data,
                promptTemplates=[_build_template_response(t) for t in templates],
            )
        )


class UpdateConfigGroupViewModel(BaseViewModel):
    """整组 upsert 配置项（General / LLM / Appearance / Data）。

    apiKey 为掩码占位（含圆点）时视为"未修改"，跳过覆盖以免把明文写成掩码。
    """

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "system_config"
    audit_enabled = True

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: UpdateConfigGroupForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)
        group = self.form.group

        if group == SystemConfigGroupEnum.PROMPT:
            self.illegal_parameters("Prompt 模板请使用模板专用接口")
            return

        rows = (
            await self.db.scalars(
                select(SystemConfig).where(
                    SystemConfig.user_id == user_id,
                    SystemConfig.group == group,
                )
            )
        ).all()
        existing = {row.key: row for row in rows}

        for key, value in self.form.items.items():
            if key in _SECRET_KEYS and isinstance(value, str) and "•" in value:
                continue  # 掩码占位，未真正修改
            if key in existing:
                existing[key].value = value
            else:
                self.db.add(SystemConfig(user_id=user_id, group=group, key=key, value=value))
        await self.db.commit()

        self._configure_audit(user_id, f"更新 {group.value} 配置")
        self.set_audit_resource_id(group.value)
        result = await _load_group(self.db, user_id, group)
        self.operating_successfully(
            ConfigGroupResponseData(group=group, items=_mask_group(group, result))
        )

    def _configure_audit(self, user_id: int, message: str) -> None:
        if self._audit_context:
            self._audit_context.category = AuditCategoryEnum.SETTINGS
            self._audit_context.actor_type = ActorTypeEnum.USER
            self._audit_context.actor_id = str(user_id)
            self._audit_context.message = message


class CreatePromptTemplateViewModel(BaseViewModel):
    """新建 Prompt 模板。启用新模板时自动停用同组其它启用项（单一启用）。"""

    audit_action = AuditActionEnum.CREATE
    audit_resource = "prompt_template"
    audit_enabled = True

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: PromptTemplateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        name = self.form.name.strip()
        if not name:
            self.illegal_parameters("模板名称不能为空")
            return

        if self.form.enabled:
            await _disable_other_templates(self.db, user_id, exclude_id=None)

        tpl_id = uuid.uuid4().hex
        value = {
            "id": tpl_id,
            "name": name,
            "description": self.form.description.strip(),
            "content": self.form.content,
            "enabled": self.form.enabled,
        }
        self.db.add(
            SystemConfig(
                user_id=user_id, group=SystemConfigGroupEnum.PROMPT, key=tpl_id, value=value
            )
        )
        await self.db.commit()

        _configure_settings_audit(self, user_id, f"新建 Prompt 模板 {name}")
        self.set_audit_resource_id(tpl_id)
        self.operating_successfully(_build_template_response(value))


class UpdatePromptTemplateViewModel(BaseViewModel):
    """更新 Prompt 模板（按 template_id 定位）。"""

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "prompt_template"
    audit_enabled = True

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        template_id: str,
        form: PromptTemplateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.template_id = template_id
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        row = await _get_template_row(self.db, user_id, self.template_id)
        if row is None:
            self.not_found("Prompt 模板不存在")
            return

        name = self.form.name.strip()
        if not name:
            self.illegal_parameters("模板名称不能为空")
            return

        if self.form.enabled:
            await _disable_other_templates(self.db, user_id, exclude_id=self.template_id)

        value = {
            "id": self.template_id,
            "name": name,
            "description": self.form.description.strip(),
            "content": self.form.content,
            "enabled": self.form.enabled,
        }
        row.value = value
        await self.db.commit()

        _configure_settings_audit(self, user_id, f"更新 Prompt 模板 {name}")
        self.set_audit_resource_id(self.template_id)
        self.operating_successfully(_build_template_response(value))


class DeletePromptTemplateViewModel(BaseViewModel):
    """删除 Prompt 模板（按 template_id 定位）。"""

    audit_action = AuditActionEnum.DELETE
    audit_resource = "prompt_template"
    audit_enabled = True

    def __init__(
        self, request: Request, db: AsyncSession, template_id: str, checker: PermissionChecker
    ) -> None:
        super().__init__(request=request)
        self.template_id = template_id
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        row = await _get_template_row(self.db, user_id, self.template_id)
        if row is None:
            self.not_found("Prompt 模板不存在")
            return

        await self.db.delete(row)
        await self.db.commit()

        _configure_settings_audit(self, user_id, f"删除 Prompt 模板 {self.template_id}")
        self.set_audit_resource_id(self.template_id)
        self.operating_successfully()


class ExportDataViewModel(BaseViewModel):
    """导出交易 / 回测数据（service stub）。"""

    audit_action = AuditActionEnum.EXPORT
    audit_resource = "data"
    audit_enabled = True

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: ExportDataForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        result = export_data(self.form.fmt, self.form.scope)
        _configure_settings_audit(self, int(self.checker.user_id), f"导出数据 {self.form.scope}")
        self.operating_successfully(
            DataActionResponseData(
                action="export",
                target=self.form.scope,
                message=result.message,
                downloadUrl=result.download_url,
            )
        )


class ClearDataViewModel(BaseViewModel):
    """清除数据（行情缓存 / 全部 Bot 与策略，service stub）。"""

    audit_action = AuditActionEnum.DELETE
    audit_resource = "data"
    audit_enabled = True

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: ClearDataForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        result = clear_data(self.form.target)
        _configure_settings_audit(self, int(self.checker.user_id), f"清除数据 {self.form.target}")
        self.set_audit_resource_id(self.form.target)
        self.operating_successfully(
            DataActionResponseData(
                action="clear",
                target=self.form.target,
                message=result.message,
                downloadUrl=None,
            )
        )


async def _get_template_row(
    db: AsyncSession, user_id: int, template_id: str
) -> SystemConfig | None:
    return await db.scalar(
        select(SystemConfig).where(
            SystemConfig.user_id == user_id,
            SystemConfig.group == SystemConfigGroupEnum.PROMPT,
            SystemConfig.key == template_id,
        )
    )


async def _disable_other_templates(
    db: AsyncSession, user_id: int, *, exclude_id: str | None
) -> None:
    """把同组其它启用模板置为停用，保证单一启用模板。"""
    rows = (
        await db.scalars(
            select(SystemConfig).where(
                SystemConfig.user_id == user_id,
                SystemConfig.group == SystemConfigGroupEnum.PROMPT,
            )
        )
    ).all()
    for row in rows:
        if row.key == exclude_id:
            continue
        value = dict(row.value)
        if value.get("enabled"):
            value["enabled"] = False
            row.value = value


def _configure_settings_audit(view_model: BaseViewModel, user_id: int, message: str) -> None:
    ctx = view_model._audit_context
    if ctx:
        ctx.category = AuditCategoryEnum.SETTINGS
        ctx.actor_type = ActorTypeEnum.USER
        ctx.actor_id = str(user_id)
        ctx.message = message
