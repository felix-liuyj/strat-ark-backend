"""风控中心 API 路由。"""

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forms.risk import (
    RiskEventCreateForm,
    RiskRuleCreateForm,
    RiskRulesBulkUpdateForm,
    RiskRuleUpdateForm,
)
from libs.auth.permissions import PermissionChecker, get_permission_checker
from libs.ctrl.db import get_db
from libs.response import BaseResponseModel, create_response
from responses.risk import (
    RiskEventResponseData,
    RiskLevelCardResponseData,
    RiskOverviewResponseData,
    RiskRuleResponseData,
)
from view_models.risk import (
    CreateRiskEventViewModel,
    CreateRiskRuleViewModel,
    ListRiskEventsViewModel,
    ListRiskLevelsViewModel,
    ListRiskRulesViewModel,
    RiskOverviewViewModel,
    UpdateRiskRulesBulkViewModel,
    UpdateRiskRuleViewModel,
)

__all__ = ("router",)

router = APIRouter()


@router.get(
    "/risk/overview",
    response_model=BaseResponseModel[RiskOverviewResponseData],
    summary="风险总览",
    description="返回总体风险状态、待处理告警数与今日亏损 / 账户回撤 / 总敞口等关键指标。",
    tags=["StratArk/风控中心"],
)
async def get_risk_overview(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(RiskOverviewViewModel, request, db, checker=checker)


@router.get(
    "/risk/levels",
    response_model=BaseResponseModel[list[RiskLevelCardResponseData]],
    summary="风控分层卡列表",
    description="返回账户 / Bot / 策略 / 持仓 / 订单 / AI 信号六层风险卡及各层状态。",
    tags=["StratArk/风控中心"],
)
async def list_risk_levels(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
) -> BaseResponseModel:
    return await create_response(ListRiskLevelsViewModel, request, checker=checker)


@router.get(
    "/risk/rules",
    response_model=BaseResponseModel[list[RiskRuleResponseData]],
    summary="风控规则列表",
    description="返回当前用户的风控规则；未配置时回落到默认规则集（只读，不落库）。",
    tags=["StratArk/风控中心"],
)
async def list_risk_rules(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListRiskRulesViewModel, request, db, checker=checker)


@router.post(
    "/risk/rules",
    response_model=BaseResponseModel[RiskRuleResponseData],
    summary="创建风控规则",
    description="新增一条指定分层与类型的风控规则。",
    tags=["StratArk/风控中心"],
)
async def create_risk_rule(
    request: Request,
    form: RiskRuleCreateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateRiskRuleViewModel, request, db, form=form, checker=checker)


@router.put(
    "/risk/rules/bulk",
    response_model=BaseResponseModel[list[RiskRuleResponseData]],
    summary="批量下发风控规则",
    description="前端「编辑风控规则」弹窗：一次提交六项阈值与三项过滤开关，全量覆盖后下发全部 Bot。",
    tags=["StratArk/风控中心"],
)
async def update_risk_rules_bulk(
    request: Request,
    form: RiskRulesBulkUpdateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(UpdateRiskRulesBulkViewModel, request, db, form=form, checker=checker)


@router.put(
    "/risk/rules/{rule_id}",
    response_model=BaseResponseModel[RiskRuleResponseData],
    summary="更新风控规则",
    description="按规则 ID 更新展示名、阈值、单位、启用状态或说明。",
    tags=["StratArk/风控中心"],
)
async def update_risk_rule(
    request: Request,
    form: RiskRuleUpdateForm,
    rule_id: int = Path(..., description="风控规则 ID"),
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(UpdateRiskRuleViewModel, request, db, rule_id=rule_id, form=form, checker=checker)


@router.get(
    "/risk/events",
    response_model=BaseResponseModel[list[RiskEventResponseData]],
    summary="风控触发记录列表",
    description="返回当前用户的风控触发记录；无记录时回落到默认事件集（只读，不落库）。",
    tags=["StratArk/风控中心"],
)
async def list_risk_events(
    request: Request,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(ListRiskEventsViewModel, request, db, checker=checker)


@router.post(
    "/risk/events",
    response_model=BaseResponseModel[RiskEventResponseData],
    summary="落地风控触发记录",
    description="风控评估命中或采取拦截动作后，写入一条风控触发记录。",
    tags=["StratArk/风控中心"],
)
async def create_risk_event(
    request: Request,
    form: RiskEventCreateForm,
    checker: PermissionChecker = Depends(get_permission_checker),
    db: AsyncSession = Depends(get_db),
) -> BaseResponseModel:
    return await create_response(CreateRiskEventViewModel, request, db, form=form, checker=checker)
