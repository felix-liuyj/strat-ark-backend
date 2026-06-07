"""用户中心域 ViewModel：API Key / OAuth 绑定 / 会话 / 2FA。

API Key 明文仅创建时返回一次（入库存哈希 + 掩码）；OAuth 绑定 / 解绑、会话退出、
2FA 开关均更新本地记录并写审计。2FA 状态复用 ``system_configs``（general 分组）持久化。
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.user_center import BindOAuthForm, CreateApiKeyForm, UpdateTwoFactorForm
from libs.auth.permissions import PermissionChecker
from libs.integrations.oauth import simulate_bind
from models.audit_log import ActorTypeEnum, AuditActionEnum, AuditCategoryEnum
from models.settings import SystemConfig, SystemConfigGroupEnum
from models.user_center import (
    OAuthBinding,
    OAuthProviderEnum,
    PlatformApiKey,
    UserSession,
)
from responses.user_center import (
    ApiKeyCreatedResponseData,
    ApiKeyResponseData,
    OAuthBindingResponseData,
    TwoFactorResponseData,
    UserSessionResponseData,
)
from view_models import BaseViewModel

__all__ = (
    "BindOAuthViewModel",
    "CreateApiKeyViewModel",
    "GetTwoFactorViewModel",
    "ListApiKeysViewModel",
    "ListOAuthBindingsViewModel",
    "ListSessionsViewModel",
    "LogoutAllSessionsViewModel",
    "LogoutSessionViewModel",
    "RevokeApiKeyViewModel",
    "UnbindOAuthViewModel",
    "UpdateTwoFactorViewModel",
)

# 2FA 状态在 system_configs(general 分组) 下的存储键。
_TWO_FACTOR_KEY = "twoFactor"


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _generate_api_key() -> tuple[str, str]:
    """生成明文密钥与掩码展示串。"""
    token = secrets.token_hex(20)
    plaintext = f"sk_live_{token}"
    prefix = f"sk_live_····{token[-4:]}"
    return plaintext, prefix


def _is_active(key: PlatformApiKey, now: datetime) -> bool:
    if key.revoked_at is not None:
        return False
    return not (key.expires_at is not None and key.expires_at < now)


class ListApiKeysViewModel(BaseViewModel):
    """平台 API Key 列表（不含明文）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        now = datetime.now(UTC)
        keys = (
            await self.db.scalars(
                select(PlatformApiKey)
                .where(PlatformApiKey.user_id == int(self.checker.user_id))
                .order_by(PlatformApiKey.id.desc())
            )
        ).all()
        self.operating_successfully([self._build(k, now) for k in keys])

    @staticmethod
    def _build(key: PlatformApiKey, now: datetime) -> ApiKeyResponseData:
        return ApiKeyResponseData(
            id=key.id,
            name=key.name,
            keyPrefix=key.key_prefix,
            permission=key.permission,
            active=_is_active(key, now),
            revoked=key.revoked_at is not None,
            lastUsedAt=_iso_or_none(key.last_used_at),
            expiresAt=_iso_or_none(key.expires_at),
        )


class CreateApiKeyViewModel(BaseViewModel):
    """创建 API Key：明文仅本次返回，入库存哈希 + 掩码。"""

    audit_action = AuditActionEnum.CREATE
    audit_resource = "platform_api_key"
    audit_enabled = True

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: CreateApiKeyForm,
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
            self.illegal_parameters("密钥名称不能为空")
            return

        plaintext, prefix = _generate_api_key()
        expires_at = (
            datetime.now(UTC) + timedelta(days=self.form.expiryDays)
            if self.form.expiryDays
            else None
        )
        key = PlatformApiKey(
            user_id=user_id,
            name=name,
            key_hash=_hash_key(plaintext),
            key_prefix=prefix,
            permission=self.form.permission,
            expires_at=expires_at,
        )
        self.db.add(key)
        await self.db.commit()
        await self.db.refresh(key)

        _configure_uc_audit(self, user_id, f"创建 API Key {name}", AuditActionEnum.CREATE)
        self.set_audit_resource_id(str(key.id))
        self.operating_successfully(
            ApiKeyCreatedResponseData(
                id=key.id,
                name=key.name,
                permission=key.permission,
                plaintextKey=plaintext,
                keyPrefix=prefix,
                expiresAt=_iso_or_none(expires_at),
            )
        )


class RevokeApiKeyViewModel(BaseViewModel):
    """撤销 API Key（置 revoked_at，保留记录）。"""

    audit_action = AuditActionEnum.DELETE
    audit_resource = "platform_api_key"
    audit_enabled = True

    def __init__(
        self, request: Request, db: AsyncSession, key_id: int, checker: PermissionChecker
    ) -> None:
        super().__init__(request=request)
        self.key_id = key_id
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        key = await self.db.get(PlatformApiKey, self.key_id)
        if key is None or key.user_id != user_id:
            self.not_found("API Key 不存在")
            return
        if key.revoked_at is not None:
            self.nothing_changed()
            return

        key.revoked_at = datetime.now(UTC)
        await self.db.commit()

        _configure_uc_audit(self, user_id, f"撤销 API Key {key.name}", AuditActionEnum.DELETE)
        self.set_audit_resource_id(str(key.id))
        self.operating_successfully()


class ListOAuthBindingsViewModel(BaseViewModel):
    """第三方账号绑定列表（四提供方全量返回，未绑定也占一项）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        rows = (
            await self.db.scalars(
                select(OAuthBinding).where(OAuthBinding.user_id == user_id)
            )
        ).all()
        by_provider = {OAuthProviderEnum(r.provider): r for r in rows}

        result = [self._build(provider, by_provider.get(provider)) for provider in OAuthProviderEnum]
        self.operating_successfully(result)

    @staticmethod
    def _build(
        provider: OAuthProviderEnum, binding: OAuthBinding | None
    ) -> OAuthBindingResponseData:
        if binding is None:
            return OAuthBindingResponseData(
                provider=provider, bound=False, accountLabel=None, linkedAt=None
            )
        return OAuthBindingResponseData(
            provider=provider,
            bound=binding.bound,
            accountLabel=binding.account_label,
            linkedAt=_iso_or_none(binding.linked_at),
        )


class BindOAuthViewModel(BaseViewModel):
    """绑定第三方账号（service stub 模拟授权）。"""

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "oauth_binding"
    audit_enabled = True

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: BindOAuthForm,
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
        provider = self.form.provider

        result = simulate_bind(provider.value, self.form.accountLabel)
        now = datetime.now(UTC)
        binding = await self.db.scalar(
            select(OAuthBinding).where(
                OAuthBinding.user_id == user_id,
                OAuthBinding.provider == provider,
            )
        )
        if binding is None:
            binding = OAuthBinding(
                user_id=user_id,
                provider=provider,
                bound=True,
                account_label=result.account_label,
                linked_at=now,
            )
            self.db.add(binding)
        else:
            if binding.bound:
                self.nothing_changed()
                return
            binding.bound = True
            binding.account_label = result.account_label
            binding.linked_at = now
        await self.db.commit()
        await self.db.refresh(binding)

        _configure_uc_audit(self, user_id, f"绑定 {provider.value} 账号", AuditActionEnum.UPDATE)
        self.set_audit_resource_id(provider.value)
        self.operating_successfully(
            OAuthBindingResponseData(
                provider=provider,
                bound=binding.bound,
                accountLabel=binding.account_label,
                linkedAt=_iso_or_none(binding.linked_at),
            )
        )


class UnbindOAuthViewModel(BaseViewModel):
    """解绑第三方账号（清空标识，保留记录）。"""

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "oauth_binding"
    audit_enabled = True

    def __init__(
        self, request: Request, db: AsyncSession, provider: OAuthProviderEnum, checker: PermissionChecker
    ) -> None:
        super().__init__(request=request)
        self.provider = provider
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        binding = await self.db.scalar(
            select(OAuthBinding).where(
                OAuthBinding.user_id == user_id,
                OAuthBinding.provider == self.provider,
            )
        )
        if binding is None or not binding.bound:
            self.nothing_changed()
            return

        binding.bound = False
        binding.account_label = None
        await self.db.commit()

        _configure_uc_audit(self, user_id, f"解绑 {self.provider.value} 账号", AuditActionEnum.UPDATE)
        self.set_audit_resource_id(self.provider.value)
        self.operating_successfully()


class ListSessionsViewModel(BaseViewModel):
    """活跃会话列表（按最近活跃倒序，当前设备置顶）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        sessions = (
            await self.db.scalars(
                select(UserSession)
                .where(
                    UserSession.user_id == int(self.checker.user_id),
                    UserSession.active.is_(True),
                )
                .order_by(UserSession.current.desc(), UserSession.id.desc())
            )
        ).all()
        self.operating_successfully([self._build(s) for s in sessions])

    @staticmethod
    def _build(session: UserSession) -> UserSessionResponseData:
        return UserSessionResponseData(
            id=session.id,
            device=session.device,
            deviceKind=session.device_kind,
            location=session.location,
            current=session.current,
            active=session.active,
            lastActiveAt=_iso_or_none(session.last_active_at),
        )


class LogoutSessionViewModel(BaseViewModel):
    """退出单个会话（非当前设备，置 active=False）。"""

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "user_session"
    audit_enabled = True

    def __init__(
        self, request: Request, db: AsyncSession, session_id: int, checker: PermissionChecker
    ) -> None:
        super().__init__(request=request)
        self.session_id = session_id
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        session = await self.db.get(UserSession, self.session_id)
        if session is None or session.user_id != user_id:
            self.not_found("会话不存在")
            return
        if session.current:
            self.illegal_parameters("无法退出当前设备会话")
            return
        if not session.active:
            self.nothing_changed()
            return

        session.active = False
        await self.db.commit()

        _configure_uc_audit(self, user_id, f"退出会话 {session.device}", AuditActionEnum.UPDATE)
        self.set_audit_resource_id(str(session.id))
        self.operating_successfully()


class LogoutAllSessionsViewModel(BaseViewModel):
    """退出全部其它会话（保留当前设备）。"""

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "user_session"
    audit_enabled = True

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        sessions = (
            await self.db.scalars(
                select(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.active.is_(True),
                    UserSession.current.is_(False),
                )
            )
        ).all()
        if not sessions:
            self.nothing_changed()
            return

        for session in sessions:
            session.active = False
        await self.db.commit()

        _configure_uc_audit(self, user_id, "退出全部其它会话", AuditActionEnum.UPDATE)
        self.operating_successfully()


class GetTwoFactorViewModel(BaseViewModel):
    """获取 2FA 状态（存于 system_configs general 分组）。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        state = await _load_two_factor(self.db, int(self.checker.user_id))
        self.operating_successfully(
            TwoFactorResponseData(
                totpEnabled=bool(state.get("totpEnabled", False)),
                requireForLiveActions=bool(state.get("requireForLiveActions", True)),
            )
        )


class UpdateTwoFactorViewModel(BaseViewModel):
    """更新 2FA 开关。"""

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "two_factor"
    audit_enabled = True

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: UpdateTwoFactorForm,
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

        value = {
            "totpEnabled": self.form.totpEnabled,
            "requireForLiveActions": self.form.requireForLiveActions,
        }
        row = await self.db.scalar(
            select(SystemConfig).where(
                SystemConfig.user_id == user_id,
                SystemConfig.group == SystemConfigGroupEnum.GENERAL,
                SystemConfig.key == _TWO_FACTOR_KEY,
            )
        )
        if row is None:
            self.db.add(
                SystemConfig(
                    user_id=user_id,
                    group=SystemConfigGroupEnum.GENERAL,
                    key=_TWO_FACTOR_KEY,
                    value=value,
                )
            )
        else:
            row.value = value
        await self.db.commit()

        _configure_uc_audit(self, user_id, "更新两步验证设置", AuditActionEnum.UPDATE)
        self.operating_successfully(
            TwoFactorResponseData(
                totpEnabled=value["totpEnabled"],
                requireForLiveActions=value["requireForLiveActions"],
            )
        )


async def _load_two_factor(db: AsyncSession, user_id: int) -> dict:
    row = await db.scalar(
        select(SystemConfig).where(
            SystemConfig.user_id == user_id,
            SystemConfig.group == SystemConfigGroupEnum.GENERAL,
            SystemConfig.key == _TWO_FACTOR_KEY,
        )
    )
    return dict(row.value) if row else {}


def _configure_uc_audit(
    view_model: BaseViewModel, user_id: int, message: str, action: AuditActionEnum
) -> None:
    ctx = view_model._audit_context
    if ctx:
        ctx.category = AuditCategoryEnum.AUTH
        ctx.actor_type = ActorTypeEnum.USER
        ctx.actor_id = str(user_id)
        ctx.action = action
        ctx.message = message
