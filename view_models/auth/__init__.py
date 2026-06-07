"""Authentication view models."""

import random
import re
import string

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from configs import get_settings
from forms.auth import (
    ChangePasswordForm,
    LoginForm,
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
from libs.custom import render_template
from libs.email import EmailController
from libs.response import ResponseStatusCodeEnum
from libs.sso import AUTH_INVALID_MESSAGE
from models.account import UserTypeEnum
from models.user import User
from responses.auth import AuthTokenResponseData, UserProfileResponseData
from view_models import BaseViewModel

__all__ = (
    "ChangePasswordViewModel",
    "GetCurrentUserViewModel",
    "LoginViewModel",
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


def _build_token_response(user: User) -> AuthTokenResponseData:
    access_token = create_access_token(
        user_id=str(user.id),
        user_type=user.user_type,
    )
    refresh_token = create_refresh_token(
        user_id=str(user.id),
        user_type=user.user_type,
    )
    return AuthTokenResponseData(
        accessToken=access_token,
        refreshToken=refresh_token,
        user=_build_user_profile(user),
    )


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

        self.operating_successfully(_build_token_response(user))


class LoginViewModel(BaseViewModel):
    """登录"""

    def __init__(self, request: Request, db: AsyncSession, form: LoginForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    async def before(self) -> None:
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

        self.operating_successfully(_build_token_response(user))


class RefreshTokenViewModel(BaseViewModel):
    """刷新 token"""

    def __init__(self, request: Request, db: AsyncSession, form: RefreshTokenForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    async def before(self) -> None:
        refresh_token = self.form.refreshToken

        payload = decode_refresh_token(refresh_token)
        if payload is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        user = await self.db.get(User, int(payload.user_id))
        if user is None or not user.is_active:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        self.operating_successfully(_build_token_response(user))


class ResetPasswordViewModel(BaseViewModel):
    """重置密码"""

    def __init__(self, request: Request, db: AsyncSession, form: ResetPasswordForm) -> None:
        super().__init__(request=request)
        self.form = form
        self.db = db

    async def before(self) -> None:
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
        self.checker.require_auth()

        display_name = self.form.displayName.strip()
        if not display_name:
            self.illegal_parameters("显示名称不能为空")
            return

        user = await self.db.get(User, int(self.checker.user_id))
        if user is None:
            self.unauthorized(AUTH_INVALID_MESSAGE)
            return

        user.display_name = display_name
        user.avatar_url = self.form.avatarUrl
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
        self.checker.require_auth()
        if self.checker.user_type != UserTypeEnum.ADMIN:
            self.forbidden("仅管理员可查看用户列表")
            return
        users = (await self.db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.id.asc()))).all()
        self.operating_successfully([_build_user_profile(u) for u in users])
