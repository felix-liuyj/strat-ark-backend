"""交易机器人 API 路由（RESTful，资源级动作 /bots/{id}/{action}）。"""

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.bot import BotCreateForm, BotSettingsUpdateForm, BotUpdateForm
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.bot import (
    BotAiSummaryResponseData,
    BotDetailResponseData,
    BotLifecycleResponseData,
    BotListItemResponseData,
    BotLiveEnableResponseData,
    BotLogEntryResponseData,
    BotPositionResponseData,
    BotRiskStatusResponseData,
    BotTradeResponseData,
)
from view_models.bots import (
    CreateBotViewModel,
    DeleteBotViewModel,
    EnableBotLiveViewModel,
    GetBotAiSummaryViewModel,
    GetBotDetailViewModel,
    GetBotLogsViewModel,
    GetBotPositionsViewModel,
    GetBotRiskStatusViewModel,
    GetBotTradesViewModel,
    ListBotsViewModel,
    RestartBotViewModel,
    StartBotViewModel,
    StopBotViewModel,
    UpdateBotSettingsViewModel,
    UpdateBotViewModel,
)

__all__ = ("router",)

router = APIRouter()

_TAGS = ["StratArk/机器人"]


@router.get(
    "/bots",
    response_model=BaseResponseModel[list[BotListItemResponseData]],
    summary="机器人列表",
    description="返回当前用户的全部交易机器人（含运行状态、策略、交易所、今日收益、持仓）。",
    tags=_TAGS,
)
async def list_bots(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListBotsViewModel, request, db, checker=checker)


@router.post(
    "/bots",
    response_model=BaseResponseModel[BotDetailResponseData],
    summary="创建机器人",
    description="按向导参数创建机器人，运行模式默认 Dry-run，必须确认风险声明；实盘需另行强确认。",
    tags=_TAGS,
)
async def create_bot(
    request: Request,
    form: BotCreateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateBotViewModel, request, db, checker=checker, form=form)


@router.get(
    "/bots/{bot_id}",
    response_model=BaseResponseModel[BotDetailResponseData],
    summary="机器人详情",
    description="返回单个机器人完整配置（参数、风控、开关、容器引用）。",
    tags=_TAGS,
)
async def get_bot_detail(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetBotDetailViewModel, request, db, checker=checker, bot_id=bot_id)


@router.put(
    "/bots/{bot_id}",
    response_model=BaseResponseModel[BotDetailResponseData],
    summary="编辑策略参数",
    description="更新机器人仓位、止损、周期、交易模式等策略参数（前端需二次确认）。",
    tags=_TAGS,
)
async def update_bot(
    request: Request,
    form: BotUpdateForm,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(UpdateBotViewModel, request, db, checker=checker, form=form, bot_id=bot_id)


@router.put(
    "/bots/{bot_id}/settings",
    response_model=BaseResponseModel[BotDetailResponseData],
    summary="更新机器人设置",
    description="更新 Telegram 通知、异常自动停机、AI 信号过滤等开关。",
    tags=_TAGS,
)
async def update_bot_settings(
    request: Request,
    form: BotSettingsUpdateForm,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        UpdateBotSettingsViewModel, request, db, checker=checker, form=form, bot_id=bot_id
    )


@router.delete(
    "/bots/{bot_id}",
    response_model=BaseResponseModel[None],
    summary="删除机器人",
    description="停止容器并永久删除该机器人的配置与数据，操作不可撤销。",
    tags=_TAGS,
)
async def delete_bot(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(DeleteBotViewModel, request, db, checker=checker, bot_id=bot_id)


@router.post(
    "/bots/{bot_id}/start",
    response_model=BaseResponseModel[BotLifecycleResponseData],
    summary="启动机器人",
    description="以当前运行模式启动机器人容器（Dry-run 无真实资金风险）。",
    tags=_TAGS,
)
async def start_bot(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(StartBotViewModel, request, db, checker=checker, bot_id=bot_id)


@router.post(
    "/bots/{bot_id}/stop",
    response_model=BaseResponseModel[BotLifecycleResponseData],
    summary="停止机器人",
    description="暂停机器人容器，当前持仓保持不变，可随时恢复。",
    tags=_TAGS,
)
async def stop_bot(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(StopBotViewModel, request, db, checker=checker, bot_id=bot_id)


@router.post(
    "/bots/{bot_id}/restart",
    response_model=BaseResponseModel[BotLifecycleResponseData],
    summary="重启机器人",
    description="重启机器人容器，短暂中断后恢复运行。",
    tags=_TAGS,
)
async def restart_bot(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(RestartBotViewModel, request, db, checker=checker, bot_id=bot_id)


@router.post(
    "/bots/{bot_id}/live-enable",
    response_model=BaseResponseModel[BotLiveEnableResponseData],
    summary="开启实盘（强确认）",
    description="提交实盘切换，仅返回状态等待风控与 2FA 确认；金额与下单全为模拟，绝不真实下单转账。",
    tags=_TAGS,
)
async def enable_bot_live(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(EnableBotLiveViewModel, request, db, checker=checker, bot_id=bot_id)


@router.get(
    "/bots/{bot_id}/trades",
    response_model=BaseResponseModel[list[BotTradeResponseData]],
    summary="机器人交易记录",
    description="返回机器人历史成交记录（模拟）。",
    tags=_TAGS,
)
async def get_bot_trades(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetBotTradesViewModel, request, db, checker=checker, bot_id=bot_id)


@router.get(
    "/bots/{bot_id}/positions",
    response_model=BaseResponseModel[list[BotPositionResponseData]],
    summary="机器人当前持仓",
    description="返回机器人当前持仓快照（模拟）。",
    tags=_TAGS,
)
async def get_bot_positions(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetBotPositionsViewModel, request, db, checker=checker, bot_id=bot_id)


@router.get(
    "/bots/{bot_id}/logs",
    response_model=BaseResponseModel[list[BotLogEntryResponseData]],
    summary="机器人运行日志",
    description="返回 Freqtrade 原始日志，可按级别筛选（INFO / TRADE / WARN / ERROR）。",
    tags=_TAGS,
)
async def get_bot_logs(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    level: str | None = Query(None, description="日志级别筛选：INFO / TRADE / WARN / ERROR"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(
        GetBotLogsViewModel, request, db, checker=checker, bot_id=bot_id, level=level
    )


@router.get(
    "/bots/{bot_id}/ai-summary",
    response_model=BaseResponseModel[BotAiSummaryResponseData],
    summary="机器人 AI 摘要",
    description="返回该机器人的 AI 投研摘要与策略信号一致性分析（模拟）。",
    tags=_TAGS,
)
async def get_bot_ai_summary(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetBotAiSummaryViewModel, request, db, checker=checker, bot_id=bot_id)


@router.get(
    "/bots/{bot_id}/risk-status",
    response_model=BaseResponseModel[BotRiskStatusResponseData],
    summary="机器人风控状态",
    description="返回机器人各风控限额的当前占用与安全判定。",
    tags=_TAGS,
)
async def get_bot_risk_status(
    request: Request,
    bot_id: int = Path(..., description="机器人 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(GetBotRiskStatusViewModel, request, db, checker=checker, bot_id=bot_id)
