"""设置读取路径不得产生隐式写入。"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from models.settings import SystemConfigGroupEnum
from view_models.settings import _load_group, _load_prompt_templates, _migrate_legacy_secret_rows


class _ScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _ReadOnlySession:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows
        self.add = MagicMock()
        self.commit = MagicMock()

    async def scalars(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(self._rows)


class SettingsReadTest(unittest.TestCase):
    def test_group_defaults_are_returned_without_write(self) -> None:
        session = _ReadOnlySession([])
        result = asyncio.run(_load_group(session, 1, SystemConfigGroupEnum.GENERAL))

        self.assertEqual("zh-CN", result["language"])
        session.add.assert_not_called()
        session.commit.assert_not_called()

    def test_empty_prompt_list_does_not_seed_on_read(self) -> None:
        session = _ReadOnlySession([])
        result = asyncio.run(_load_prompt_templates(session, 1))

        self.assertEqual([], result)
        session.add.assert_not_called()
        session.commit.assert_not_called()

    def test_legacy_secret_migrates_only_on_explicit_write_path(self) -> None:
        row = SimpleNamespace(value="legacy-plain-key")

        with patch("view_models.settings._secret_storage", return_value="fernet::encrypted") as encrypt:
            _migrate_legacy_secret_rows({"apiKey": row})

        encrypt.assert_called_once_with("legacy-plain-key")
        self.assertEqual("fernet::encrypted", row.value)


if __name__ == "__main__":
    unittest.main()
