"""Alembic 迁移图静态守门。"""

import unittest

from alembic.config import Config
from alembic.script import ScriptDirectory


class MigrationGraphTest(unittest.TestCase):
    def test_revision_ids_are_unique_and_history_is_linear(self) -> None:
        script = ScriptDirectory.from_config(Config("alembic.ini"))
        revisions = list(script.walk_revisions())
        revision_ids = [revision.revision for revision in revisions]

        self.assertEqual(len(revision_ids), len(set(revision_ids)))
        self.assertEqual(["0004"], script.get_heads())
        self.assertEqual(["0004", "0003", "0002", "0001"], revision_ids)


if __name__ == "__main__":
    unittest.main()
