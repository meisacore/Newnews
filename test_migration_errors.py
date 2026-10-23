import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch
import psycopg

from migrate_storage import safe_failure, connection_check
from storage import PostgresTarget


class MigrationDiagnosticTests(unittest.TestCase):
    def test_categories_never_echo_connection_credentials(self):
        cases = [
            ("password authentication failed", "authentication failed"),
            ("Tenant or user not found", "pooler host and username"),
            ("connection timeout expired", "timed out"),
            ("could not translate host name", "hostname could not be resolved"),
            ("connection refused", "refused the connection"),
            ("SSL connection failed", "encrypted database connection"),
            ("server closed the connection unexpectedly", "closed unexpectedly"),
            ("unrecognized problem", "SQLSTATE unavailable"),
        ]
        for error, expected in cases:
            with self.subTest(error=error):
                secret = "private%40password"
                exc = psycopg.OperationalError(
                    error + " postgresql://user:" + secret + "@host/postgres"
                )
                result = safe_failure(exc)
                self.assertIn(expected, result)
                self.assertNotIn(secret, result)
                self.assertNotIn("postgresql://", result)
                self.assertNotIn("user:", result)

    def test_connection_check_only_reads_and_does_not_print_url(self):
        target = PostgresTarget("postgresql://user:private-password@host/postgres")
        raw = MagicMock()
        raw.execute.return_value.fetchone.return_value = (True,)
        output = io.StringIO()
        with patch("psycopg.connect") as connect, redirect_stdout(output):
            connect.return_value.__enter__.return_value = raw
            connection_check(target)
        connect.assert_called_once_with(target.url, autocommit=True, connect_timeout=10)
        self.assertTrue(
            all(
                call.args[0].startswith("SELECT ")
                for call in raw.execute.call_args_list
            )
        )
        self.assertIn("Connection successful", output.getvalue())
        self.assertNotIn("private-password", output.getvalue())

    def test_sqlite_error_is_not_reported_as_a_supabase_connection_error(self):
        import sqlite3

        self.assertIn("local SQLite", safe_failure(sqlite3.OperationalError("locked")))


if __name__ == "__main__":
    unittest.main()
