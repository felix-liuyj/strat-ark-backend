"""GET 读取路径不得隐式 seed、迁移或提交事务。"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi import Request

from libs.auth.permissions import PermissionChecker
from models.engine import EngineKindEnum
from view_models.engine import _AdminEngineViewModel
from view_models.notification import ListNotificationChannelsViewModel
from view_models.subscription import ListPlansViewModel


class _ScalarResult:
    def all(self) -> list[object]:
        return []


class _ReadOnlySession:
    def __init__(self) -> None:
        self.add = MagicMock()
        self.commit = AsyncMock()
        self.flush = AsyncMock()

    async def scalar(self, _statement: object) -> None:
        return None

    async def scalars(self, _statement: object) -> _ScalarResult:
        return _ScalarResult()


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
            "client": ("127.0.0.1", 1234),
        }
    )


class ReadOnlyEndpointTest(unittest.TestCase):
    def test_missing_engine_returns_virtual_view_without_write(self) -> None:
        session = _ReadOnlySession()
        view_model = _AdminEngineViewModel(_request("/engines"))
        view_model.db = session

        engine = asyncio.run(view_model._get_engine(EngineKindEnum.FREQTRADE))

        self.assertLess(engine.id, 0)
        session.add.assert_not_called()
        session.flush.assert_not_awaited()
        session.commit.assert_not_awaited()

    def test_plan_catalog_read_does_not_seed(self) -> None:
        session = _ReadOnlySession()
        view_model = ListPlansViewModel(_request("/plans"), session)

        asyncio.run(view_model.before())

        self.assertEqual([], view_model.data)
        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    def test_notification_channel_read_does_not_seed(self) -> None:
        session = _ReadOnlySession()
        checker = PermissionChecker()
        checker.is_authenticated = True
        checker.user_id = "1"
        view_model = ListNotificationChannelsViewModel(
            _request("/notification-channels"), session, checker
        )

        asyncio.run(view_model.before())

        self.assertEqual([], view_model.data)
        session.add.assert_not_called()
        session.commit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
