"""交易所账户 view models。

增删改查 + 连接测试 + 同步余额 + 查看权限 + 设为默认。API Key/Secret 加密存储
（stub：保存掩码 + 占位密文），不明文回显。外部交易所交互一律走 libs.integrations.exchange。
"""

from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forms.exchange import (
    ExchangeAccountCreateForm,
    ExchangeAccountUpdateForm,
    ExchangeConnectionTestForm,
)
from libs.auth.permissions import PermissionChecker
from libs.integrations import exchange as exchange_service
from models.exchange import (
    ExchangeAccount,
    ExchangePermissionEnum,
    ExchangeStatusEnum,
)
from responses.exchange import (
    ExchangeAccountResponseData,
    ExchangeBalanceResponseData,
    ExchangeConnectionTestResponseData,
    ExchangePermissionResponseData,
    ExchangeSecurityCheckResponseData,
)
from view_models.common.base import BaseViewModel

__all__ = (
    "CreateExchangeAccountViewModel",
    "DeleteExchangeAccountViewModel",
    "GetExchangePermissionViewModel",
    "ListExchangeAccountsViewModel",
    "SetDefaultExchangeAccountViewModel",
    "SyncExchangeBalanceViewModel",
    "TestExchangeConnectionViewModel",
    "TestRawExchangeConnectionViewModel",
    "UpdateExchangeAccountViewModel",
)

_PERMISSION_LABELS: dict[ExchangePermissionEnum, str] = {
    ExchangePermissionEnum.READ_ONLY: "exchanges.permReadOnly",
    ExchangePermissionEnum.READ_TRADE: "exchanges.permReadTrade",
    ExchangePermissionEnum.READ_TRADE_WITHDRAW: "exchanges.permReadTradeWithdraw",
}


def _mask_api_key(api_key: str) -> str:
    """生成 API Key 掩码（仅保留尾 4 位），不明文存储或回显。"""
    tail = api_key.strip()[-4:] if len(api_key.strip()) >= 4 else api_key.strip()
    return f"····{tail}"


def _encrypt_secret(api_secret: str) -> str:
    """加密 API Secret（stub）：真实实现走 KMS/fernet，此处仅占位密文，绝不可逆出明文。"""
    return f"enc::{len(api_secret.strip())}"


def _format_usdt(amount: float) -> str:
    return f"{amount:,.0f} USDT"


def _build_checks(account: ExchangeAccount) -> list[ExchangeSecurityCheckResponseData]:
    return [
        ExchangeSecurityCheckResponseData(
            key="withdraw",
            label="exchanges.checkNoWithdraw" if account.withdraw_disabled else "exchanges.checkWithdrawOn",
            passed=account.withdraw_disabled,
        ),
        ExchangeSecurityCheckResponseData(
            key="ipWhitelist",
            label="exchanges.checkIpOn" if account.ip_whitelist_enabled else "exchanges.checkIpSuggest",
            passed=account.ip_whitelist_enabled,
        ),
        ExchangeSecurityCheckResponseData(
            key="tradeOnly",
            label="exchanges.checkTradeOnly" if account.trade_only else "exchanges.checkTooWide",
            passed=account.trade_only,
        ),
    ]


def _build_account_data(account: ExchangeAccount) -> ExchangeAccountResponseData:
    return ExchangeAccountResponseData(
        id=account.id,
        name=account.name,
        provider=account.provider,
        status=account.status,
        permission=account.permission,
        permissionLabel=_PERMISSION_LABELS.get(account.permission, "exchanges.permReadTrade"),
        apiKeyMask=account.api_key_mask,
        ipWhitelist=account.ip_whitelist,
        isDefault=account.is_default,
        balanceUsdt=account.balance_usdt,
        balanceLabel=_format_usdt(account.balance_usdt),
        lastSyncedAt=account.last_synced_at,
        checks=_build_checks(account),
    )


class _AuthedExchangeViewModel(BaseViewModel):
    """登录态 + 归属校验的交易所基类。"""

    def __init__(self, request: Request, db: AsyncSession, checker: PermissionChecker) -> None:
        super().__init__(request=request)
        self.db = db
        self.checker = checker

    async def _load_owned_account(self, account_id: int) -> ExchangeAccount | None:
        """加载当前用户名下的交易所账户，越权或不存在返回 None。"""
        account = await self.db.get(ExchangeAccount, account_id)
        if account is None or account.user_id != int(self.checker.user_id):
            return None
        return account


class ListExchangeAccountsViewModel(_AuthedExchangeViewModel):
    """交易所账户列表（仅本人）。"""

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        statement = (
            select(ExchangeAccount)
            .where(ExchangeAccount.user_id == int(self.checker.user_id))
            .order_by(ExchangeAccount.is_default.desc(), ExchangeAccount.id.asc())
        )
        accounts = (await self.db.scalars(statement)).all()
        self.operating_successfully([_build_account_data(account) for account in accounts])


class CreateExchangeAccountViewModel(_AuthedExchangeViewModel):
    """添加交易所账户（API Key 加密存储 + 连接测试回填安全检查）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: ExchangeAccountCreateForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.form = form

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()

        name = self.form.name.strip()
        if not name:
            self.illegal_parameters("账户名称不能为空")
            return
        if not self.form.apiKey.strip() or not self.form.apiSecret.strip():
            self.illegal_parameters("API Key 与 Secret 不能为空")
            return

        # 通过 service 做连接测试 + 权限探测，回填安全检查位（mock）。
        connection = exchange_service.test_connection(self.form.provider.value, self.form.apiKey, self.form.apiSecret)
        permissions = exchange_service.fetch_permissions(
            self.form.provider.value, self.form.apiKey, self.form.apiSecret
        )
        ip_whitelist = (self.form.ipWhitelist or "").strip()

        # 首个账户自动设为默认。
        existing_count = await self.db.scalar(
            select(ExchangeAccount.id).where(ExchangeAccount.user_id == int(self.checker.user_id)).limit(1)
        )
        account = ExchangeAccount(
            user_id=int(self.checker.user_id),
            name=name,
            provider=self.form.provider,
            status=ExchangeStatusEnum.CONNECTED if connection.ok else ExchangeStatusEnum.ERROR,
            permission=(
                ExchangePermissionEnum.READ_TRADE
                if not permissions.can_withdraw
                else ExchangePermissionEnum.READ_TRADE_WITHDRAW
            ),
            api_key_mask=_mask_api_key(self.form.apiKey),
            api_secret_cipher=_encrypt_secret(self.form.apiSecret),
            ip_whitelist=ip_whitelist,
            is_default=existing_count is None,
            withdraw_disabled=not permissions.can_withdraw,
            ip_whitelist_enabled=bool(ip_whitelist) or permissions.ip_whitelisted,
            trade_only=permissions.can_trade and not permissions.can_withdraw,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        self.operating_successfully(_build_account_data(account))


class UpdateExchangeAccountViewModel(_AuthedExchangeViewModel):
    """更新交易所账户（重置凭证则重新掩码加密）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: ExchangeAccountUpdateForm,
        checker: PermissionChecker,
        account_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.form = form
        self.account_id = account_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        account = await self._load_owned_account(self.account_id)
        if account is None:
            self.not_found("交易所账户不存在")
            return

        if self.form.name is not None:
            name = self.form.name.strip()
            if not name:
                self.illegal_parameters("账户名称不能为空")
                return
            account.name = name
        if self.form.apiKey is not None and self.form.apiKey.strip():
            account.api_key_mask = _mask_api_key(self.form.apiKey)
        if self.form.apiSecret is not None and self.form.apiSecret.strip():
            account.api_secret_cipher = _encrypt_secret(self.form.apiSecret)
        if self.form.ipWhitelist is not None:
            ip_whitelist = self.form.ipWhitelist.strip()
            account.ip_whitelist = ip_whitelist
            account.ip_whitelist_enabled = bool(ip_whitelist)

        await self.db.commit()
        await self.db.refresh(account)
        self.operating_successfully(_build_account_data(account))


class DeleteExchangeAccountViewModel(_AuthedExchangeViewModel):
    """删除交易所账户（连带加密凭证）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        account_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.account_id = account_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        account = await self._load_owned_account(self.account_id)
        if account is None:
            self.not_found("交易所账户不存在")
            return

        was_default = account.is_default
        await self.db.delete(account)
        await self.db.flush()

        # 删除默认账户后，将剩余最早的账户提升为默认。
        if was_default:
            fallback = await self.db.scalar(
                select(ExchangeAccount)
                .where(ExchangeAccount.user_id == int(self.checker.user_id))
                .order_by(ExchangeAccount.id.asc())
                .limit(1)
            )
            if fallback is not None:
                fallback.is_default = True

        await self.db.commit()
        self.operating_successfully()


class TestExchangeConnectionViewModel(_AuthedExchangeViewModel):
    """连接测试（不改库，仅返回 service 结果）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        account_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.account_id = account_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        account = await self._load_owned_account(self.account_id)
        if account is None:
            self.not_found("交易所账户不存在")
            return

        result = exchange_service.test_connection(account.provider.value, account.api_key_mask, "")
        self.operating_successfully(_build_connection_response(result))


class TestRawExchangeConnectionViewModel(_AuthedExchangeViewModel):
    """未保存账户连接测试（不入库、不持久化凭证）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        form: ExchangeConnectionTestForm,
        checker: PermissionChecker,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.form = form

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        if not self.form.apiKey.strip() or not self.form.apiSecret.strip():
            self.illegal_parameters("API Key 与 Secret 不能为空")
            return
        result = exchange_service.test_connection(
            self.form.provider.value, self.form.apiKey, self.form.apiSecret
        )
        self.operating_successfully(_build_connection_response(result))


class SyncExchangeBalanceViewModel(_AuthedExchangeViewModel):
    """同步余额（service 拉取后回写缓存）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        account_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.account_id = account_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        account = await self._load_owned_account(self.account_id)
        if account is None:
            self.not_found("交易所账户不存在")
            return

        balance = exchange_service.fetch_balance(account.provider.value, account.api_key_mask, "")
        synced_at = balance.synced_at.strftime("%Y-%m-%d %H:%M")
        account.balance_usdt = balance.total_usdt
        account.last_synced_at = synced_at
        await self.db.commit()

        self.operating_successfully(
            ExchangeBalanceResponseData(
                balanceUsdt=balance.total_usdt,
                availableUsdt=balance.available_usdt,
                syncedAt=synced_at,
                breakdown=balance.breakdown,
            )
        )


class GetExchangePermissionViewModel(_AuthedExchangeViewModel):
    """查看权限详情（service 探测）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        account_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.account_id = account_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        account = await self._load_owned_account(self.account_id)
        if account is None:
            self.not_found("交易所账户不存在")
            return

        permissions = exchange_service.fetch_permissions(account.provider.value, account.api_key_mask, "")
        self.operating_successfully(
            ExchangePermissionResponseData(
                canRead=permissions.can_read,
                canTrade=permissions.can_trade,
                canWithdraw=permissions.can_withdraw,
                ipWhitelisted=permissions.ip_whitelisted,
                ipWhitelist=permissions.ip_whitelist,
            )
        )


class SetDefaultExchangeAccountViewModel(_AuthedExchangeViewModel):
    """设为默认交易所（互斥：取消同用户其它默认）。"""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        checker: PermissionChecker,
        account_id: int,
    ) -> None:
        super().__init__(request=request, db=db, checker=checker)
        self.account_id = account_id

    async def before(self) -> None:
        await super().before()
        self.checker.require_auth()
        account = await self._load_owned_account(self.account_id)
        if account is None:
            self.not_found("交易所账户不存在")
            return

        others = (
            await self.db.scalars(
                select(ExchangeAccount).where(
                    ExchangeAccount.user_id == int(self.checker.user_id),
                    ExchangeAccount.is_default.is_(True),
                )
            )
        ).all()
        for other in others:
            other.is_default = False
        account.is_default = True
        account.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(account)
        self.operating_successfully(_build_account_data(account))


def _build_connection_response(
    result: exchange_service.ExchangeConnectionResult,
) -> ExchangeConnectionTestResponseData:
    return ExchangeConnectionTestResponseData(
        ok=result.ok,
        latencyMs=result.latency_ms,
        message=result.message,
        permissionSafe=result.permission_safe,
    )
