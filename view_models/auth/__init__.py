"""Authentication view models."""

import random
import re
import secrets
import string
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from configs import get_settings
from forms.auth import (
    ChangePasswordForm,
    LoginForm,
    OAuthExchangeForm,
    RefreshTokenForm,
    RegisterForm,
    ResetPasswordForm,
    SendVerificationCodeForm,
    SendVerificationPurposeEnum,
    UpdateProfileForm,
)
from libs.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from libs.auth.permissions import PermissionChecker
from libs.auth.session import (
    is_refresh_jti_active,
    register_refresh_jti,
    revoke_refresh_jti,
)
from libs.ctrl.cloud.oss import AliCloudOssBucketController
from libs.custom import render_template
from libs.email import EmailController
from libs.integrations.oauth_login import VerifiedOAuthIdentity, exchange_oauth_code
from libs.response import ResponseStatusCodeEnum
from libs.sso import AUTH_INVALID_MESSAGE
from libs.upload_rules import validate_oss_url
from models.account import UserTypeEnum
from models.oauth_identity import OAuthIdentity
from models.user import User
from models.user_center import OAuthBinding, OAuthProviderEnum
from responses.auth import AuthTokenResponseData, UserProfileResponseData
from view_models.common.base import BaseViewModel

__all__ = (
    "ChangePasswordViewModel",
    "GetCurrentUserViewModel",
    "LoginViewModel",
    "LogoutViewModel",
    "OAuthExchangeViewModel",
    "RefreshTokenViewModel",
    "RegisterViewModel",
    "ResetPasswordViewModel",
    "SendVerificationCodeViewModel",
    "UpdateProfileViewModel",
)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_MIN_PASSWORD_LENGTH = 6


def _set_error_state(view_model: BaseViewModel, code: ResponseStatusCodeEnum, message: str) -> None:
    view_model.status_code = code
    view_model.message = message
    view_model.data = None


def _resolve_registration_user_type(email: str) -> UserTypeEnum:
    return UserTypeEnum.ADMIN if get_settings().is_admin_email(email) else UserTypeEnum.CLIENT


def _build_user_profile(user: User) -> UserProfileResponseData:
    return UserProfileResponseData(
        id=user.id,
        email=user.email,
        displayName=user.display_name,
        userType=user.user_type,
        plan=user.plan,
        isAdmin=user.user_type == UserTypeEnum.ADMIN,
        isVerified=user.is_verified,
        avatarUrl=user.avatar_url,
    )


async def _issue_session(user: User) -> AuthTokenResponseData:
    """统一签发出口：邮箱密码 / 注册 / OAuth / 刷新都走这里。

    access 短 TTL；refresh 携带 jti 并登记 Redis 白名单（rotation + 登出即时吊销的前提）。
    """
    access_token = create_access_token(
        user_id=str(user.id),
        user_type=user.user_type,
    )
    refresh_token, jti, ttl_seconds = create_refresh_token(
        user_id=str(user.id),
        user_type=user.user_type,
    )
    await register_refresh_jti(str(user.id), jti, ttl_seconds)
    return AuthTokenResponseData(
        accessToken=access_token,
        refreshToken=refresh_token,
        user=_build_user_profile(user),
    )


def _oauth_display_name(identity: VerifiedOAuthIdentity) -> str:
    if identity.name:
        return identity.name[:100]
    if identity.email and "@" in identity.email:
        return identity.email.split("@", 1)[0][:100]
    return f"{identity.provider}-{identity.subject[:12]}"


def _oauth_email(identity: VerifiedOAuthIdentity) -> str | None:
    return identity.email.strip().lower() if identity.email else None


def _random_oauth_password() -> str:
    return secrets.token_urlsafe(32)


class SendVerificationCodeViewModel(BaseViewModel):
    """发送验证码"""

    def __init__(self, request: Request, db: AsyncSession, form: SendVerificationCodeForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    @staticmethod
    def _generate_otp_code() -> str:
        return "".join(random.choices(string.digits, k=BaseViewModel.OTP_CODE_LENGTH))

    async def _send_otp_email(self, email: str, purpose: str) -> None:
        from libs import redis_cache
        from libs.logger import logger

        settings = get_settings()
        if not settings.SMTP_HOST or not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            raise RuntimeError("SMTP 配置不完整，无法发送验证码邮件")

        code = self._generate_otp_code()
        code_key = self._otp_code_key(purpose, email)
        limit_key = self._otp_limit_key(email)

        await redis_cache.set(code_key, code, ex=self.OTP_EXPIRE_SECONDS)
        await redis_cache.set(limit_key, "1", ex=self.OTP_RATE_LIMIT_SECONDS)

        subject_map = {"register": "注册验证码", "reset": "密码重置验证码"}
        subject = f"{settings.APP_NAME} - {subject_map.get(purpose, '验证码')}"
        html_body = render_template(
            "verification_code.html",
            code=code,
            purpose=subject_map.get(purpose, "验证"),
            expire_minutes=self.OTP_EXPIRE_SECONDS // 60,
            app_name=settings.APP_NAME,
            # 从配置（OSS bucket + region + BRAND_LOGO_OSS_PATH）拼出 logo URL；
            # OSS 字段缺失时返回 None，模板层留空 logo 区域。
            logo_url=settings.brand_logo_url,
        )

        try:
            controller = EmailController(
                from_email=settings.SMTP_SENDER or settings.SMTP_USERNAME,
                to_email=email,
                subject=subject,
                email_body=html_body,
                use_tls=settings.SMTP_USE_SSL,
            )
            success = await controller.send_email_with_ssl()
            if not success:
                raise RuntimeError("SMTP 发送返回失败")
        except Exception as exc:
            logger.error(f"Failed to send verification email to {email}: {exc}")
            raise RuntimeError("验证码邮件发送失败，请检查邮箱地址或稍后重试") from exc

    async def before(self) -> None:
        await super().before()
        from libs import redis_cache

        email = self.form.email.strip().lower()
        purpose = self.form.purpose

        if not _EMAIL_RE.match(email):
            self.illegal_parameters("邮箱格式不正确")
            return

        existing_limit = await redis_cache.get(self._otp_limit_key(email))
        if existing_limit is not None:
            _set_error_state(
                self,
                ResponseStatusCodeEnum.AUTH_VERIFICATION_CODE_RATE_LIMITED,
                "验证码发送过于频繁，请 60 秒后重试",
            )
            return

        if purpose == SendVerificationPurposeEnum.REGISTER:
            existing = await self.db.scalar(select(User).where(User.email == email))
            if existing is not None:
                _set_error_state(
                    self,
                    ResponseStatusCodeEnum.AUTH_EMAIL_ALREADY_REGISTERED,
                    "该邮箱已注册",
                )
                return

        if purpose == SendVerificationPurposeEnum.RESET:
            existing = await self.db.scalar(select(User).where(User.email == email))
            if existing is None:
                _set_error_state(
                    self,
                    ResponseStatusCodeEnum.AUTH_ACCOUNT_NOT_FOUND,
                    "该邮箱尚未注册",
                )
                return

        await self._send_otp_email(email, purpose.value)
        self.operating_successfully()


class RegisterViewModel(BaseViewModel):
    """注册"""

    def __init__(self, request: Request, db: AsyncSession, form: RegisterForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    async def before(self) -> None:
        await super().before()
        email = self.form.email.strip().lower()
        password = self.form.password
        display_name = self.form.displayName.strip()
        code = self.form.otp.strip()

        if not _EMAIL_RE.match(email):
            self.illegal_parameters("邮箱格式不正确")
            return

        if len(password) < _MIN_PASSWORD_LENGTH:
            self.illegal_parameters(f"密码长度不能少于 {_MIN_PASSWORD_LENGTH} 位")
            return

        if not display_name:
            self.illegal_parameters("显示名称不能为空")
            return

        existing = await self.db.scalar(select(User).where(User.email == email))
        if existing is not None:
            _set_error_state(
                self,
                ResponseStatusCodeEnum.AUTH_EMAIL_ALREADY_REGISTERED,
                "该邮箱已注册",
            )
            return

        if not await self._verify_otp(email, code, "register"):
            _set_error_state(
                self,
                ResponseStatusCodeEnum.AUTH_VERIFICATION_CODE_INVALID,
                "验证码无效或已过期",
            )
            return

        user = User(
            email=email,
            display_name=display_name,
            user_type=_resolve_registration_user_type(email),
            is_active=True,
            is_verified=True,
        )
        user.set_password(password)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        self.operating_successfully(await _issue_session(user))


class LoginViewModel(BaseViewModel):
    """登录"""

    def __init__(self, request: Request, db: AsyncSession, form: LoginForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    async def before(self) -> None:
        await super().before()
        email = self.form.email.strip().lower()
        password = self.form.password

        user = await self.db.scalar(select(User).where(User.email == email))
        if user is None:
            _set_error_state(
                self,
                ResponseStatusCodeEnum.AUTH_ACCOUNT_NOT_FOUND,
                "该邮箱尚未注册",
            )
            return

        if not user.verify_password(password):
            _set_error_state(
                self,
                ResponseStatusCodeEnum.AUTH_PASSWORD_INCORRECT,
                "密码错误，请重新输入",
            )
            return

        if not user.is_active:
            _set_error_state(
                self,
                ResponseStatusCodeEnum.AUTH_ACCOUNT_DISABLED,
                "账号已被禁用",
            )
            return

        self.operating_successfully(await _issue_session(user))


class OAuthExchangeViewModel(BaseViewModel):
    """OAuth 授权码换取自家 session。"""

    def __init__(self, request: Request, db: AsyncSession, form: OAuthExchangeForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    async def before(self) -> None:
        await super().before()
        identity = await self._exchange_identity()
        if identity is None:
            return
        user = await self._resolve_user(identity)
        if user is None:
            return
        await self._sync_binding(user, identity)
        await self.db.commit()
        await self.db.refresh(user)
        self.operating_successfully(await _issue_session(user))

    async def _exchange_identity(self) -> VerifiedOAuthIdentity | None:
        try:
            return await exchange_oauth_code(
                self.form.provider.value,
                self.form.code,
                self.form.redirectUri,
                self.form.codeVerifier,
            )
        except ValueError as exc:
            self.illegal_parameters(str(exc))
            return None

    async def _resolve_user(self, identity: VerifiedOAuthIdentity) -> User | None:
        oauth_identity = await self._get_oauth_identity(identity)
        if oauth_identity is not None:
            return await self._resolve_existing_user(oauth_identity, identity)
        return await self._create_oauth_user(identity)

    async def _get_oauth_identity(self, identity: VerifiedOAuthIdentity) -> OAuthIdentity | None:
        return await self.db.scalar(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == identity.provider,
                OAuthIdentity.subject == identity.subject,
            )
        )

    async def _resolve_existing_user(self, row: OAuthIdentity, identity: VerifiedOAuthIdentity) -> User | None:
        user = await self.db.get(User, row.user_id)
        if user is None or not user.is_active:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return None
        self._refresh_oauth_identity(row, identity)
        self._refresh_user_profile(user, identity)
        return user

    async def _create_oauth_user(self, identity: VerifiedOAuthIdentity) -> User | None:
        email = _oauth_email(identity)
        if not email:
            self.illegal_parameters("第三方账号未返回可用邮箱")
            return None
        if await self.db.scalar(select(User).where(User.email == email)) is not None:
            self.illegal_parameters("该邮箱已被其它登录方式使用，请先用原方式登录后绑定第三方账号")
            return None
        user = self._new_oauth_user(identity, email)
        self.db.add(user)
        await self.db.flush()
        self.db.add(self._new_oauth_identity(user.id, identity))
        return user

    @staticmethod
    def _new_oauth_user(identity: VerifiedOAuthIdentity, email: str) -> User:
        user = User(
            email=email,
            display_name=_oauth_display_name(identity),
            user_type=_resolve_registration_user_type(email),
            is_active=True,
            is_verified=identity.email_verified,
            avatar_url=identity.picture,
        )
        user.set_password(_random_oauth_password())
        return user

    @staticmethod
    def _new_oauth_identity(user_id: int, identity: VerifiedOAuthIdentity) -> OAuthIdentity:
        now = datetime.now(UTC)
        return OAuthIdentity(
            user_id=user_id,
            provider=identity.provider,
            subject=identity.subject,
            profile_email=_oauth_email(identity),
            display_name=identity.name,
            avatar_url=identity.picture,
            raw_claims=identity.raw_claims,
            linked_at=now,
            refreshed_at=now,
        )

    @staticmethod
    def _refresh_oauth_identity(row: OAuthIdentity, identity: VerifiedOAuthIdentity) -> None:
        row.profile_email = _oauth_email(identity)
        row.display_name = identity.name
        row.avatar_url = identity.picture
        row.raw_claims = identity.raw_claims
        row.refreshed_at = datetime.now(UTC)

    @staticmethod
    def _refresh_user_profile(user: User, identity: VerifiedOAuthIdentity) -> None:
        if identity.name:
            user.display_name = _oauth_display_name(identity)
        if identity.picture:
            user.avatar_url = identity.picture

    async def _sync_binding(self, user: User, identity: VerifiedOAuthIdentity) -> None:
        provider = OAuthProviderEnum(identity.provider)
        binding = await self.db.scalar(
            select(OAuthBinding).where(OAuthBinding.user_id == user.id, OAuthBinding.provider == provider)
        )
        if binding is None:
            self.db.add(self._new_binding(user.id, provider, identity))
            return
        binding.bound = True
        binding.account_label = identity.email or identity.subject

    @staticmethod
    def _new_binding(user_id: int, provider: OAuthProviderEnum, identity: VerifiedOAuthIdentity) -> OAuthBinding:
        return OAuthBinding(
            user_id=user_id,
            provider=provider,
            bound=True,
            account_label=identity.email or identity.subject,
            linked_at=datetime.now(UTC),
        )


class RefreshTokenViewModel(BaseViewModel):
    """刷新 token（rotation：旧 jti 校验白名单后立即吊销，签发新对；旧 token 重放即被拦）。"""

    def __init__(self, request: Request, db: AsyncSession, form: RefreshTokenForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    async def before(self) -> None:
        await super().before()
        refresh_token = self.form.refreshToken

        payload = decode_refresh_token(refresh_token)
        if payload is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        if not await is_refresh_jti_active(payload.user_id, payload.jti):
            # 已被 rotation 消费 / 已登出 / 已吊销：拒绝并不再签发。
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        user = await self.db.get(User, int(payload.user_id))
        if user is None or not user.is_active:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        await revoke_refresh_jti(payload.user_id, payload.jti)
        self.operating_successfully(await _issue_session(user))


class LogoutViewModel(BaseViewModel):
    """登出：吊销 refresh token 的 jti，使其立即失效（access 短 TTL 自然过期）。

    幂等：token 无效 / 已过期 / 已吊销均返回成功，不暴露 token 状态。
    """

    def __init__(self, request: Request, db: AsyncSession, form: RefreshTokenForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    async def before(self) -> None:
        await super().before()
        payload = decode_refresh_token(self.form.refreshToken)
        if payload is not None:
            await revoke_refresh_jti(payload.user_id, payload.jti)
        self.operating_successfully()


class ResetPasswordViewModel(BaseViewModel):
    """重置密码"""

    def __init__(self, request: Request, db: AsyncSession, form: ResetPasswordForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    async def before(self) -> None:
        await super().before()
        email = self.form.email.strip().lower()
        code = self.form.otp.strip()
        new_password = self.form.newPassword

        if len(new_password) < _MIN_PASSWORD_LENGTH:
            self.illegal_parameters(f"密码长度不能少于 {_MIN_PASSWORD_LENGTH} 位")
            return

        user = await self.db.scalar(select(User).where(User.email == email))
        if user is None:
            _set_error_state(
                self,
                ResponseStatusCodeEnum.AUTH_ACCOUNT_NOT_FOUND,
                "该邮箱尚未注册",
            )
            return

        if not await self._verify_otp(email, code, "reset"):
            _set_error_state(
                self,
                ResponseStatusCodeEnum.AUTH_VERIFICATION_CODE_INVALID,
                "验证码无效或已过期",
            )
            return

        user.set_password(new_password)
        await self.db.commit()
        self.operating_successfully()


class ChangePasswordViewModel(BaseViewModel):
    """修改密码（需登录）"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: ChangePasswordForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        old_password = self.form.oldPassword
        new_password = self.form.newPassword

        if len(new_password) < _MIN_PASSWORD_LENGTH:
            self.illegal_parameters(f"密码长度不能少于 {_MIN_PASSWORD_LENGTH} 位")
            return

        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        if not user.verify_password(old_password):
            _set_error_state(
                self,
                ResponseStatusCodeEnum.AUTH_PASSWORD_INCORRECT,
                "当前密码错误",
            )
            return

        user.set_password(new_password)
        await self.db.commit()
        self.operating_successfully()


class GetCurrentUserViewModel(BaseViewModel):
    """获取当前登录用户信息"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        self.operating_successfully(_build_user_profile(user))


class UpdateProfileViewModel(BaseViewModel):
    """更新用户资料（昵称 + 头像 URL）"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: UpdateProfileForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request)
        self.form = form
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        display_name = self.form.displayName.strip()
        if not display_name:
            self.illegal_parameters("显示名称不能为空")
            return

        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        # 头像入库校验：空 → 置空；与现值相同（含 OAuth 第三方头像）→ 保持不动；
        # 新值必须是当前 OSS Bucket avatars 目录下的对象（经签名直传产生的 publicUrl）。
        avatar_url = (self.form.avatarUrl or "").strip()
        new_avatar: str | None = None
        if avatar_url:
            if avatar_url == (user.avatar_url or ""):
                new_avatar = user.avatar_url
            else:
                try:
                    object_path = validate_oss_url(avatar_url, AliCloudOssBucketController().expected_host)
                    if not object_path.startswith("avatars/"):
                        raise ValueError("头像必须上传到 avatars 目录")
                except ValueError as exc:
                    self.illegal_parameters(str(exc))
                    return
                except RuntimeError:
                    # ALI_OSS_* 未配置时无法校验归属，也不接受任意外部 URL。
                    self.illegal_parameters("对象存储未配置，暂不支持更换头像")
                    return
                new_avatar = avatar_url

        user.display_name = display_name
        user.avatar_url = new_avatar
        await self.db.commit()
        await self.db.refresh(user)
        self.operating_successfully(_build_user_profile(user))


class ListUsersViewModel(BaseViewModel):
    """管理员查看全部用户 (id / 邮箱 / 显示名 / 用户类型 / 头像)。

    用于 ProjectList 首张卡片"用户文件夹"九宫格 + 所有用户弹窗的数据源。
    返回字段沿用 UserProfileResponseData, 与 /auth/me 同 schema。
    """

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.checker = checker
        self.db = db

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        if self.checker.user_type != UserTypeEnum.ADMIN:
            self.forbidden("仅管理员可查看用户列表")
            return
        users = (await self.db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.id.asc()))).all()
        self.operating_successfully([_build_user_profile(u) for u in users])
