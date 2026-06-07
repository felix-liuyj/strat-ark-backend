"""交易所账户 API 路由（RESTful，资源级动作 /exchanges/{id}/{action}）。"""

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.exchange import (
    ExchangeAccountCreateForm,
    ExchangeAccountUpdateForm,
    ExchangeConnectionTestForm,
)
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.exchange import (
    ExchangeAccountResponseData,
    ExchangeBalanceResponseData,
    ExchangeConnectionTestResponseData,
    ExchangePermissionResponseData,
)
from view_models.exchanges import (
    CreateExchangeAccountViewModel,
    DeleteExchangeAccountViewModel,
    GetExchangePermissionViewModel,
    ListExchangeAccountsViewModel,
    SetDefaultExchangeAccountViewModel,
    SyncExchangeBalanceViewModel,
    TestExchangeConnectionViewModel,
    TestRawExchangeConnectionViewModel,
    UpdateExchangeAccountViewModel,
)

__all__ = ("router",)

router = APIRouter()

_TAGS = ["StratArk/交易所账户"]


@router.get(
    "/exchanges",
    response_model=BaseResponseModel[list[ExchangeAccountResponseData]],
    summary="交易所账户列表",
    description="返回当前登录用户绑定的全部交易所账户（含余额、权限、安全检查项），默认账户优先。",
    tags=_TAGS,
)
async def list_exchange_accounts(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListExchangeAccountsViewModel, request, db, checker=checker)


@router.post(
    "/exchanges",
    response_model=BaseResponseModel[ExchangeAccountResponseData],
    summary="添加交易所账户",
    description="绑定新的交易所账户，API Key/Secret 加密存储且不明文回显，自动连接测试并回填安全检查项。",
    tags=_TAGS,
)
async def create_exchange_account(
    request: Request,
    form: ExchangeAccountCreateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateExchangeAccountViewModel, request, db, checker=checker, form=form)


@router.post(
    "/exchanges/test",
    response_model=BaseResponseModel[ExchangeConnectionTestResponseData],
    summary="测试未保存交易所凭证",
    description="在添加账户前校验 API Key/Secret 可用性；仅用于本次请求，不保存凭证。",
    tags=_TAGS,
)
async def test_raw_exchange_connection(
    request: Request,
    form: ExchangeConnectionTestForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(TestRawExchangeConnectionViewModel, request, db, checker=checker, form=form)


@router.put(
    "/exchanges/{exchange_id}",
    response_model=BaseResponseModel[ExchangeAccountResponseData],
    summary="更新交易所账户",
    description="更新账户名称或重置 API 凭证、IP 白名单；凭证留空表示不更新。",
    tags=_TAGS,
)
async def update_exchange_account(
    request: Request,
    form: ExchangeAccountUpdateForm,
    exchange_id: int = Path(..., description="交易所账户 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        UpdateExchangeAccountViewModel, request, db, checker=checker, form=form, account_id=exchange_id
    )


@router.delete(
    "/exchanges/{exchange_id}",
    response_model=BaseResponseModel[None],
    summary="删除交易所账户",
    description="移除交易所连接与已加密的 API Key；删除默认账户后自动提升剩余最早账户为默认。",
    tags=_TAGS,
)
async def delete_exchange_account(
    request: Request,
    exchange_id: int = Path(..., description="交易所账户 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(DeleteExchangeAccountViewModel, request, db, checker=checker, account_id=exchange_id)


@router.post(
    "/exchanges/{exchange_id}/test",
    response_model=BaseResponseModel[ExchangeConnectionTestResponseData],
    summary="连接测试",
    description="校验账户 API 凭证可用性与权限安全性，返回握手延迟与安全判定。",
    tags=_TAGS,
)
async def test_exchange_connection(
    request: Request,
    exchange_id: int = Path(..., description="交易所账户 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(TestExchangeConnectionViewModel, request, db, checker=checker, account_id=exchange_id)


@router.post(
    "/exchanges/{exchange_id}/sync-balance",
    response_model=BaseResponseModel[ExchangeBalanceResponseData],
    summary="同步余额",
    description="从交易所拉取最新余额（折合 USDT）并回写缓存，返回各币种明细。",
    tags=_TAGS,
)
async def sync_exchange_balance(
    request: Request,
    exchange_id: int = Path(..., description="交易所账户 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(SyncExchangeBalanceViewModel, request, db, checker=checker, account_id=exchange_id)


@router.get(
    "/exchanges/{exchange_id}/permissions",
    response_model=BaseResponseModel[ExchangePermissionResponseData],
    summary="查看权限",
    description="返回该账户 API Key 的读取 / 交易 / 提现 / IP 白名单权限明细。",
    tags=_TAGS,
)
async def get_exchange_permissions(
    request: Request,
    exchange_id: int = Path(..., description="交易所账户 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetExchangePermissionViewModel, request, db, checker=checker, account_id=exchange_id)


@router.post(
    "/exchanges/{exchange_id}/set-default",
    response_model=BaseResponseModel[ExchangeAccountResponseData],
    summary="设为默认交易所",
    description="将该账户设为默认交易所，互斥取消同用户其它默认账户。",
    tags=_TAGS,
)
async def set_default_exchange_account(
    request: Request,
    exchange_id: int = Path(..., description="交易所账户 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        SetDefaultExchangeAccountViewModel, request, db, checker=checker, account_id=exchange_id
    )
