import os
import unittest
from unittest.mock import patch
from paths import database_path, world_path
from storage import PostgresTarget


class StorageConfigTests(unittest.TestCase):
    def test_remote_url_enforces_tls_and_hides_password(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://user:private-test-password@db.example.com:5432/postgres"
            },
        ):
            target = database_path()
        self.assertIsInstance(target, PostgresTarget)
        self.assertIn("sslmode=require", target.url)
        self.assertNotIn("private-test-password", str(target))
        self.assertNotIn("private-test-password", repr(target))
        self.assertEqual(world_path(target, "bull").schema, "norx_bull")
        self.assertEqual(world_path(target, "bull").url, target.url)

    def test_unsafe_pooling_or_schema_rejected(self):
        for changes in [
            {"DATABASE_URL": "postgresql://user:pass@db.example.com:6543/postgres"},
            {
                "DATABASE_URL": "postgresql://user:pass@db.example.com:5432/postgres?sslmode=disable"
            },
            {
                "DATABASE_URL": "postgresql://user:pass@db.example.com:5432/postgres",
                "NORX_PG_SCHEMA_PREFIX": "bad-schema;",
            },
        ]:
            with patch.dict(os.environ, changes), self.assertRaises(ValueError):
                database_path()


if __name__ == "__main__":
    unittest.main()
