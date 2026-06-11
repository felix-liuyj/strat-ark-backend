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
from libs.crypto import decrypt_text, encrypt_text
from libs.totp import generate_secret, provisioning_uri, verify_code
from models.audit_log import ActorTypeEnum, AuditActionEnum, AuditCategoryEnum
from models.settings import SystemConfig, SystemConfigGroupEnum
from models.user import User
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
    TwoFactorSetupResponseData,
    UserSessionResponseData,
)
from view_models.common.base import BaseViewModel

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
    "SetupTwoFactorViewModel",
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
    """绑定第三方账号。真实 OAuth 授权流程未完成前拒绝直接绑定。"""

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
        provider = self.form.provider

        self.set_audit_resource_id(provider.value)
        self.operating_failed(f"{provider.value} 账号绑定尚未接入真实 OAuth 授权流程")


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
        self.operating_successfully(_build_two_factor(state))


class SetupTwoFactorViewModel(BaseViewModel):
    """开始 TOTP 绑定：生成 secret（加密暂存为 pending）并返回 otpauth 绑定信息。

    不改变 totpEnabled——需再调 PUT /user/two-factor 携带验证码确认后才真正启用。
    """

    audit_action = AuditActionEnum.UPDATE
    audit_resource = "two_factor"
    audit_enabled = True

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        user_id = int(self.checker.user_id)

        user = await self.db.get(User, user_id)
        if user is None:
            self.unauthorized()
            return

        secret = generate_secret()
        state = await _load_two_factor(self.db, user_id)
        state["pendingSecretCipher"] = encrypt_text(secret)
        await _save_two_factor(self.db, user_id, state)

        _configure_uc_audit(self, user_id, "发起两步验证绑定", AuditActionEnum.UPDATE)
        self.operating_successfully(
            TwoFactorSetupResponseData(
                secret=secret,
                otpauthUri=provisioning_uri(secret, user.email),
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

        state = await _load_two_factor(self.db, user_id)
        currently_enabled = bool(state.get("totpEnabled") and state.get("secretCipher"))

        if self.form.totpEnabled and not currently_enabled:
            # 开启：用 setup 暂存的 pending secret 校验验证码，通过才转正。
            pending = decrypt_text(state.get("pendingSecretCipher"))
            if not pending:
                self.illegal_parameters("请先获取绑定二维码（/user/two-factor/setup）")
                return
            if not verify_code(pending, self.form.totpCode or ""):
                self.illegal_parameters("验证码错误或已过期，请重新输入")
                return
            state["secretCipher"] = encrypt_text(pending)
            state["pendingSecretCipher"] = None
            state["totpEnabled"] = True
        elif not self.form.totpEnabled and currently_enabled:
            # 关闭：用当前 active secret 校验验证码，防止他人在已登录会话中擅自关闭。
            active = decrypt_text(state.get("secretCipher"))
            if not active or not verify_code(active, self.form.totpCode or ""):
                self.illegal_parameters("关闭两步验证需输入当前验证码")
                return
            state["secretCipher"] = None
            state["pendingSecretCipher"] = None
            state["totpEnabled"] = False

        # requireForLiveActions 可独立调整（不涉及密钥校验）。
        state["requireForLiveActions"] = self.form.requireForLiveActions
        await _save_two_factor(self.db, user_id, state)

        _configure_uc_audit(self, user_id, "更新两步验证设置", AuditActionEnum.UPDATE)
        self.operating_successfully(_build_two_factor(state))


async def _load_two_factor(db: AsyncSession, user_id: int) -> dict:
    row = await db.scalar(
        select(SystemConfig).where(
            SystemConfig.user_id == user_id,
            SystemConfig.group == SystemConfigGroupEnum.GENERAL,
            SystemConfig.key == _TWO_FACTOR_KEY,
        )
    )
    return dict(row.value) if row else {}


async def _save_two_factor(db: AsyncSession, user_id: int, value: dict) -> None:
    row = await db.scalar(
        select(SystemConfig).where(
            SystemConfig.user_id == user_id,
            SystemConfig.group == SystemConfigGroupEnum.GENERAL,
            SystemConfig.key == _TWO_FACTOR_KEY,
        )
    )
    if row is None:
        db.add(
            SystemConfig(
                user_id=user_id, group=SystemConfigGroupEnum.GENERAL, key=_TWO_FACTOR_KEY, value=value
            )
        )
    else:
        # JSON 列需整体重新赋值触发脏标记（就地改 dict 不会被 ORM 检测）。
        row.value = dict(value)
    await db.commit()


def _build_two_factor(state: dict) -> TwoFactorResponseData:
    """从存储状态构造响应；secret 密文绝不外泄，totpEnabled 以 active secret 是否存在为准。"""
    return TwoFactorResponseData(
        totpEnabled=bool(state.get("totpEnabled") and state.get("secretCipher")),
        requireForLiveActions=bool(state.get("requireForLiveActions", True)),
        pendingSetup=bool(state.get("pendingSecretCipher")),
    )


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
