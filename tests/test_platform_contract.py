"""Smoke contract for the StratArk platform API surface.

These tests intentionally avoid the FastAPI lifespan so they do not require a
running PostgreSQL or Redis service. They prove that the application imports,
the planned module routes are registered, and auth role tokens are parseable.
"""

import asyncio
import unittest
import warnings

from fastapi.routing import APIRoute
from starlette.requests import Request

from libs.auth.jwt import create_access_token
from libs.auth.permissions import PermissionChecker
from libs.response import ResponseStatusCodeEnum, create_response
from main import app
from models.account import UserTypeEnum
from view_models.audit import ListAuditLogsViewModel
from view_models.engine import ListEnginesViewModel

warnings.filterwarnings("ignore", message="The HMAC key is .*", category=Warning)


REQUIRED_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/auth/login"),
    ("GET", "/auth/me"),
    ("GET", "/exchanges"),
    ("POST", "/exchanges"),
    ("POST", "/exchanges/{exchange_id}/test"),
    ("GET", "/bots"),
    ("POST", "/bots"),
    ("POST", "/bots/{bot_id}/start"),
    ("POST", "/bots/{bot_id}/live-enable"),
    ("GET", "/strategies"),
    ("POST", "/strategies/import"),
    ("GET", "/strategies/{strategy_id}/versions"),
    ("GET", "/backtests"),
    ("POST", "/backtests"),
    ("GET", "/backtests/{task_id}"),
    ("GET", "/backtests/{task_id}/result"),
    ("POST", "/backtests/{task_id}/ai-review"),
    ("POST", "/ai/market-analysis"),
    ("GET", "/signals"),
    ("POST", "/signals/{signal_id}/approve"),
    ("GET", "/risk/overview"),
    ("PUT", "/risk/rules/bulk"),
    ("GET", "/trades"),
    ("GET", "/positions"),
    ("GET", "/market/overview"),
    ("GET", "/market/tickers/{symbol:path}"),
    ("GET", "/notifications"),
    ("GET", "/notification-channels"),
    ("PUT", "/notification-subscriptions"),
    ("GET", "/plans"),
    ("GET", "/subscription"),
    ("POST", "/subscription/change"),
    ("GET", "/engines"),
    ("POST", "/engines/{engine_kind}/operations"),
    ("GET", "/audit-logs"),
    ("GET", "/audit-logs/verify-chain"),
    ("GET", "/settings"),
    ("PUT", "/settings/group"),
    ("GET", "/user/api-keys"),
    ("GET", "/user/oauth-bindings"),
    ("GET", "/user/two-factor"),
)

ADMIN_ONLY_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/engines"),
    ("POST", "/engines/{engine_kind}/operations"),
    ("GET", "/audit-logs"),
    ("GET", "/audit-logs/kpi"),
)


def _api_routes() -> list[APIRoute]:
    return [route for route in app.routes if isinstance(route, APIRoute)]


def _route_methods() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in _api_routes():
        for method in route.methods or set():
            if method in {"HEAD", "OPTIONS"}:
                continue
            pairs.add((method, route.path))
    return pairs


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )


async def _load_checker(user_type: UserTypeEnum) -> PermissionChecker:
    checker = PermissionChecker()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        token = create_access_token(user_id="2", user_type=user_type)
        await checker.load_from_token(token)
    return checker


class PlatformContractTest(unittest.TestCase):
    def test_required_route_surface_is_registered(self) -> None:
        registered = _route_methods()
        missing = [route for route in REQUIRED_ROUTES if route not in registered]
        self.assertEqual([], missing)
        self.assertGreaterEqual(len(registered), 100)

    def test_admin_domain_routes_remain_registered(self) -> None:
        registered = _route_methods()
        missing = [route for route in ADMIN_ONLY_ROUTES if route not in registered]
        self.assertEqual([], missing)

    def test_resource_paths_do_not_use_action_collection_segments(self) -> None:
        bad_segments = {"search", "list", "create"}
        offenders: list[str] = []
        for route in _api_routes():
            segments = {segment for segment in route.path.split("/") if segment}
            if segments & bad_segments:
                offenders.append(route.path)
        self.assertEqual([], sorted(set(offenders)))

    def test_openapi_schema_builds_for_registered_routes(self) -> None:
        schema = app.openapi()
        self.assertIn("paths", schema)
        self.assertIn("/bots", schema["paths"])
        self.assertIn("/notification-channels", schema["paths"])
        self.assertIn("/audit-logs", schema["paths"])

    def test_jwt_permission_checker_maps_user_type(self) -> None:
        async def load(token: str) -> PermissionChecker:
            checker = PermissionChecker()
            await checker.load_from_token(token)
            return checker

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            admin_token = create_access_token(user_id="1", user_type=UserTypeEnum.ADMIN)
            client_token = create_access_token(user_id="2", user_type=UserTypeEnum.CLIENT)
            admin = asyncio.run(load(admin_token))
            client = asyncio.run(load(client_token))

        self.assertTrue(admin.is_authenticated)
        self.assertEqual(UserTypeEnum.ADMIN, admin.user_type)
        self.assertTrue(client.is_authenticated)
        self.assertEqual(UserTypeEnum.CLIENT, client.user_type)

    def test_admin_view_models_forbid_client_user(self) -> None:
        async def guard_codes() -> list[ResponseStatusCodeEnum]:
            checker = await _load_checker(UserTypeEnum.CLIENT)
            engine = await create_response(
                ListEnginesViewModel, _request("/engines"), None, checker=checker
            )
            audit = await create_response(
                ListAuditLogsViewModel,
                _request("/audit-logs"),
                None,
                checker=checker,
                category=None,
                role=None,
                start_time=None,
                end_time=None,
                page_no=1,
                page_size=20,
            )
            return [engine.code, audit.code]

        self.assertEqual(
            [ResponseStatusCodeEnum.FORBIDDEN, ResponseStatusCodeEnum.FORBIDDEN],
            asyncio.run(guard_codes()),
        )


if __name__ == "__main__":
    unittest.main()
