"""Preview must release SQLite handles before temporary files are removed."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from economy import Market
from migrate_storage import import_world
from storage import PostgresTarget


class MigrationPreviewTests(unittest.TestCase):
    def test_backup_handles_closed_before_temporary_directory_cleanup(self):
        real_connect = sqlite3.connect
        real_temporary_directory = tempfile.TemporaryDirectory
        handles = []
        case = self

        class CheckedDirectory(real_temporary_directory):
            def __exit__(self, *args):
                # Linux permits unlinking open SQLite files; Windows does not.
                # Require the connections to be closed on either platform.
                case.assertTrue(handles)
                for handle in handles:
                    with case.assertRaises(sqlite3.ProgrammingError):
                        handle.execute("SELECT 1")
                return super().__exit__(*args)

        def connect(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            handles.append(db)
            return db

        with real_temporary_directory() as folder:
            source = Path(folder) / "world.sqlite3"
            market = Market(source)
            before = market.account("did:privy:saved")
            target = PostgresTarget("postgresql://not-used.invalid/postgres")
            with (
                patch("migrate_storage.tempfile.TemporaryDirectory", CheckedDirectory),
                patch("migrate_storage.sqlite3.connect", side_effect=connect),
                patch("migrate_storage.postgres_worker_lock") as remote,
            ):
                counts = import_world(source, target)
            remote.assert_not_called()
            self.assertGreater(counts["accounts"], 0)
            self.assertEqual(before, market.account("did:privy:saved"))


if __name__ == "__main__":
    unittest.main()
