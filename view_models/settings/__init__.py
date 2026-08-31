"""设置域 ViewModel：系统配置读写 + Prompt 模板 CRUD + 数据导出 / 清除。

配置按 用户 + 分组 + key 存于 ``system_configs``；缺失默认值只在响应中合并，读取
不写库。LLM API Key 经 Fernet 加密入库，响应层只返回掩码。
"""

import base64
import csv
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.settings import (
    ClearDataForm,
    ExportDataForm,
    LlmConnectionTestForm,
    PromptTemplateForm,
    UpdateConfigGroupForm,
)
from libs import redis_cache
from libs.auth.permissions import PermissionChecker
from libs.crypto import CIPHER_PREFIX, decrypt_text, encrypt_text
from libs.integrations.data_ops import test_llm_gateway
from models.audit_log import ActorTypeEnum, AuditActionEnum, AuditCategoryEnum
from models.backtests import BacktestTask
from models.bot import Bot
from models.settings import SystemConfig, SystemConfigGroupEnum
from models.strategy import Strategy, StrategyVersion
from models.trade import Order, Position, Trade
from responses.settings import (
    ConfigGroupResponseData,
    DataActionResponseData,
    LlmConnectionTestResponseData,
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
    "TestLlmConnectionViewModel",
    "UpdateConfigGroupViewModel",
    "UpdatePromptTemplateViewModel",
)

# 敏感字段集合：响应层掩码、不回明文。
_SECRET_KEYS: frozenset[str] = frozenset({"apiKey"})
_CLEAR_TARGET_MARKET = "market_cache"
_CLEAR_TARGET_BOTS = "bots_strategies"
_EXPORT_SCOPES = {"all", "trades", "backtests"}
_EXPORT_FORMATS = {"csv", "json"}

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
    "apiKey": "",
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

def _secret_plaintext(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if text.startswith(CIPHER_PREFIX):
        return decrypt_text(text) or ""
    return text


def _secret_storage(value: Any) -> str:
    text = str(value or "").strip()
    return encrypt_text(text) if text else ""


def _mask_secret(value: Any) -> str:
    """掩码敏感字符串：保留前缀与尾 4 位，中间以圆点替代。"""
    text = _secret_plaintext(value)
    if not text:
        return ""
    if len(text) <= 8:
        return "••••"
    head = text[:6]
    tail = text[-4:]
    return f"{head}••••{tail}"


def _is_masked_secret(value: str) -> bool:
    return "•" in value or "*" in value


def _mask_group(group: SystemConfigGroupEnum, items: dict[str, Any]) -> dict[str, Any]:
    if group != SystemConfigGroupEnum.LLM:
        return items
    return {k: (_mask_secret(v) if k in _SECRET_KEYS else v) for k, v in items.items()}


def _coerce_config_value(group: SystemConfigGroupEnum, key: str, value: Any) -> Any:
    if group == SystemConfigGroupEnum.LLM and key in _SECRET_KEYS:
        return _secret_storage(value)
    return value


def _migrate_legacy_secret_rows(existing: dict[str, SystemConfig]) -> None:
    """在显式 LLM 配置写入时，把历史明文密钥迁移为 Fernet 密文。"""
    for key in _SECRET_KEYS:
        row = existing.get(key)
        if row is None or not isinstance(row.value, str) or not row.value:
            continue
        if not row.value.startswith(CIPHER_PREFIX):
            row.value = _secret_storage(row.value)


async def _load_group(db: AsyncSession, user_id: int, group: SystemConfigGroupEnum) -> dict[str, Any]:
    """只读加载标量分组；缺失项仅在响应中合并默认值，不在 GET 路径写库。"""
    rows = (
        await db.scalars(
            select(SystemConfig).where(
                SystemConfig.user_id == user_id,
                SystemConfig.group == group,
            )
        )
    ).all()
    defaults = dict(_GROUP_DEFAULTS.get(group, {}))
    defaults.update({row.key: row.value for row in rows})
    return defaults


async def _load_prompt_templates(db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    """只读加载 Prompt 模板；为空时返回空列表，由显式创建接口负责写入。"""
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
        if group == SystemConfigGroupEnum.LLM:
            _migrate_legacy_secret_rows(existing)

        for key, value in self.form.items.items():
            if key in _SECRET_KEYS and isinstance(value, str) and "•" in value:
                continue  # 掩码占位，未真正修改
            stored_value = _coerce_config_value(group, key, value)
            if key in existing:
                existing[key].value = stored_value
            else:
                self.db.add(SystemConfig(user_id=user_id, group=group, key=key, value=stored_value))
        await self.db.commit()

        self._configure_audit(user_id, f"更新 {group.value} 配置")
        self.set_audit_resource_id(group.value)
        result = await _load_group(self.db, user_id, group)
        self.operating_successfully(ConfigGroupResponseData(group=group, items=_mask_group(group, result)))

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
        self.db.add(SystemConfig(user_id=user_id, group=SystemConfigGroupEnum.PROMPT, key=tpl_id, value=value))
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

    def __init__(self, request: Request, db: AsyncSession, template_id: str, checker: PermissionChecker) -> None:
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
    """导出当前用户交易 / 回测数据。"""

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

        fmt = self.form.fmt.strip().lower()
        scope = self.form.scope.strip().lower()
        if fmt not in _EXPORT_FORMATS or scope not in _EXPORT_SCOPES:
            self.illegal_parameters("导出格式或范围不支持")
            return
        rows = await _export_rows(self.db, int(self.checker.user_id), scope)
        download_url = _build_download_url(rows, fmt, scope)
        _configure_settings_audit(self, int(self.checker.user_id), f"导出数据 {self.form.scope}")
        self.operating_successfully(
            DataActionResponseData(
                action="export",
                target=self.form.scope,
                message=f"已导出 {len(rows)} 条记录",
                downloadUrl=download_url,
            )
        )


class ClearDataViewModel(BaseViewModel):
    """清除当前用户数据或系统行情缓存。"""

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

        target = self.form.target.strip()
        if target == _CLEAR_TARGET_MARKET:
            count = await _clear_market_cache()
            message = f"已清除 {count} 条行情缓存"
        elif target == _CLEAR_TARGET_BOTS:
            count = await _clear_bots_and_strategies(self.db, int(self.checker.user_id))
            message = f"已清除 {count} 条 Bot / 策略相关记录"
        else:
            self.illegal_parameters("清除目标不支持")
            return
        _configure_settings_audit(self, int(self.checker.user_id), f"清除数据 {self.form.target}")
        self.set_audit_resource_id(self.form.target)
        self.operating_successfully(
            DataActionResponseData(
                action="clear",
                target=self.form.target,
                message=message,
                downloadUrl=None,
            )
        )


class TestLlmConnectionViewModel(BaseViewModel):
    """测试 LLM 模型网关连接，不落库。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: LlmConnectionTestForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        provider = self.form.provider.strip()
        endpoint = self.form.endpoint.strip()
        api_key = await self._resolve_api_key()
        if not provider or not endpoint or not api_key:
            self.illegal_parameters("Provider、Endpoint 与 API Key 不能为空")
            return
        result = test_llm_gateway(provider, self.form.model.strip(), endpoint, api_key)
        self.operating_successfully(
            LlmConnectionTestResponseData(
                ok=result.ok,
                provider=provider,
                model=self.form.model.strip(),
                latencyMs=result.latency_ms,
                message=result.message,
            )
        )

    async def _resolve_api_key(self) -> str:
        api_key = self.form.apiKey.strip()
        if api_key and not _is_masked_secret(api_key):
            return api_key
        llm = await _load_group(self.db, int(self.checker.user_id), SystemConfigGroupEnum.LLM)
        return _secret_plaintext(llm.get("apiKey", "")).strip()


async def _export_rows(db: AsyncSession, user_id: int, scope: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if scope in ("all", "trades"):
        trades = (await db.scalars(select(Trade).where(Trade.user_id == user_id).order_by(Trade.id.asc()))).all()
        rows.extend(_trade_row(item) for item in trades)
    if scope in ("all", "backtests"):
        tasks = (
            await db.scalars(
                select(BacktestTask).where(BacktestTask.user_id == user_id).order_by(BacktestTask.id.asc())
            )
        ).all()
        rows.extend(_backtest_row(item) for item in tasks)
    return rows


def _trade_row(item: Trade) -> dict[str, Any]:
    return {
        "type": "trade",
        "id": item.id,
        "symbol": item.symbol,
        "side": str(item.side),
        "status": str(item.status),
        "botName": item.bot_name,
        "pnl": item.pnl,
        "pnlPct": item.pnl_pct,
        "openedAt": item.opened_at,
        "closedAt": item.closed_at,
    }


def _backtest_row(item: BacktestTask) -> dict[str, Any]:
    return {
        "type": "backtest",
        "id": item.id,
        "strategyName": item.strategy_name,
        "symbol": item.symbol,
        "timeframe": item.timeframe,
        "status": str(item.status),
        "totalReturn": item.total_return,
        "maxDrawdown": item.max_drawdown,
        "sharpe": item.sharpe,
        "trades": item.trades,
    }


def _build_download_url(rows: list[dict[str, Any]], fmt: str, scope: str) -> str:
    payload = _serialize_rows(rows, fmt)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    mime = "text/csv" if fmt == "csv" else "application/json"
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return f"data:{mime};name=stratark-{scope}-{stamp}.{fmt};base64,{encoded}"


def _serialize_rows(rows: list[dict[str, Any]], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2)
    fieldnames = sorted({key for row in rows for key in row} or {"type"})
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


async def _clear_market_cache() -> int:
    keys = [key async for key in redis_cache.scan_iter(match="market:*")]
    if not keys:
        return 0
    await redis_cache.delete(*keys)
    return len(keys)


async def _clear_bots_and_strategies(db: AsyncSession, user_id: int) -> int:
    strategy_ids = select(Strategy.id).where(Strategy.user_id == user_id)
    statements = [
        delete(Order).where(Order.user_id == user_id),
        delete(Position).where(Position.user_id == user_id),
        delete(Trade).where(Trade.user_id == user_id),
        delete(BacktestTask).where(BacktestTask.user_id == user_id),
        delete(Bot).where(Bot.user_id == user_id),
        delete(StrategyVersion).where(StrategyVersion.strategy_id.in_(strategy_ids)),
        delete(Strategy).where(Strategy.user_id == user_id),
    ]
    count = 0
    for statement in statements:
        result = await db.execute(statement)
        count += result.rowcount or 0
    await db.commit()
    return count


async def _get_template_row(db: AsyncSession, user_id: int, template_id: str) -> SystemConfig | None:
    return await db.scalar(
        select(SystemConfig).where(
            SystemConfig.user_id == user_id,
            SystemConfig.group == SystemConfigGroupEnum.PROMPT,
            SystemConfig.key == template_id,
        )
    )


async def _disable_other_templates(db: AsyncSession, user_id: int, *, exclude_id: str | None) -> None:
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
