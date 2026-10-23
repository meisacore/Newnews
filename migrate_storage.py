"""Preview or import SQLite snapshots into empty PostgreSQL world schemas.

Stop NORX and all workers first. DATABASE_URL stays in the environment, never in
command arguments. Original files are read-only; imports are atomic per world.
"""

import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from economy import Market, SCHEMA
from paths import database_path, world_path, PROJECT_ROOT
from scenarios import SCENARIOS
from worker import worker_lock
from storage import PostgresTarget, connection, postgres_worker_lock

TABLES = (
    "accounts",
    "holdings",
    "coins",
    "trades",
    "quotes",
    "meta",
    "launches",
    "agent_personas",
    "agent_grants",
)


def import_world(source, target, apply=False):
    from psycopg import sql

    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError("Source database does not exist")
    with worker_lock(source), tempfile.TemporaryDirectory() as folder:
        snapshot = Path(folder) / "snapshot.sqlite3"
        # SQLite's backup API includes committed WAL data and does not mutate
        # the original. Supply/schema upgrades run only on this temporary copy.
        # sqlite3.Connection.__exit__ commits/rolls back but does not close the
        # handle. Windows cannot remove the snapshot while either handle lives.
        with closing(
            sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        ) as original:
            with closing(sqlite3.connect(snapshot)) as copied:
                original.backup(copied)
        market = Market(snapshot)
        with market.connection() as local:
            counts = {
                table: local.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in TABLES
            }
            if not apply:
                return counts
            with postgres_worker_lock(target), connection(target) as db:
                db.executescript(SCHEMA)
                try:
                    if any(
                        db.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone()
                        for table in TABLES
                    ):
                        raise ValueError(
                            "Destination world is not empty; import refused"
                        )
                    for table in TABLES:
                        columns = [
                            r[1] for r in local.execute(f'PRAGMA table_info("{table}")')
                        ]
                        query = sql.SQL("COPY {} ({}) FROM STDIN").format(
                            sql.Identifier(table),
                            sql.SQL(",").join(map(sql.Identifier, columns)),
                        )
                        with db.raw.cursor().copy(query) as copy:
                            for row in local.execute(f'SELECT * FROM "{table}"'):
                                copy.write_row(tuple(row))
                        actual = db.execute(
                            f'SELECT COUNT(*) FROM "{table}"'
                        ).fetchone()[0]
                        if actual != counts[table]:
                            raise ValueError("Import row count mismatch")
                    # Preserve old trade IDs, then advance the PostgreSQL sequence.
                    db.raw.execute(
                        "SELECT setval(pg_get_serial_sequence('trades','id'), COALESCE(MAX(id),1), COUNT(*)>0) FROM trades"
                    )
                    # Pending quotes are short-lived and must be previewed again
                    # after a storage switch. Completed idempotency results survive.
                    db.execute("UPDATE quotes SET expires=0 WHERE result IS NULL")
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
        return counts


def connection_check(target):
    """Read-only check using the same connection parameters as the worker lock."""
    import psycopg

    with psycopg.connect(target.url, autocommit=True, connect_timeout=10) as db:
        db.execute("SELECT 1")
        can_create = db.execute(
            "SELECT has_database_privilege(current_user,current_database(),'CREATE')"
        ).fetchone()[0]
    print(
        "Connection successful: PostgreSQL is reachable and credentials were accepted."
    )
    if not can_create:
        raise ValueError("Database role needs CREATE privilege for NORX world schemas")
    print("Schema creation permission: OK. No market data was changed.")


def safe_failure(exc):
    """Classify driver errors without echoing DSNs, passwords or row contents."""
    import psycopg
    from filelock import Timeout

    if isinstance(exc, PermissionError):
        return "Local file permission error. Stop NORX and database viewers; check write access to data and your temporary folder."
    if isinstance(exc, Timeout):
        return "A NORX worker still owns the source or destination world. Stop the backend and all standalone workers, then retry."
    if isinstance(exc, psycopg.Error):
        detail = str(exc).lower()  # Inspect only; never print the raw driver error.
        code = exc.sqlstate
        if "tenant or user not found" in detail:
            return "Supabase could not match the pooler host and username to your project. Copy the Session pooler URI again from Connect; keep the postgres.PROJECT_REF username."
        if (
            code in ("28P01", "28000")
            or "password authentication failed" in detail
            or "authentication failed" in detail
        ):
            return "Database authentication failed. Re-enter the Supabase database password (not an API key), and check the Session pooler username. Rebuild DATABASE_URL with the password percent-encoded."
        if (
            "translate host name" in detail
            or "getaddrinfo" in detail
            or "name or service not known" in detail
        ):
            return "The database hostname could not be resolved. Check the Session pooler hostname and your DNS/network connection."
        if "timeout" in detail or "timed out" in detail:
            return "The database connection or operation timed out. Check that the Supabase project is active and that your network allows outbound port 5432."
        if "connection refused" in detail:
            return "The database refused the connection. Check the Session pooler host/port and that your Supabase project is running."
        if "too many" in detail or "maxclients" in detail or code == "53300":
            return "The database or pooler has reached its connection limit. Stop duplicate NORX backends and workers, then retry."
        if code == "42501":
            return "The database role lacks permission for NORX schemas/tables. Use the backend database connection from Supabase Connect, not a browser API key."
        if "ssl" in detail or "tls" in detail or "certificate" in detail:
            return "The encrypted database connection failed. Keep sslmode=require (or a correctly configured verify-full connection) and check for network interception."
        if "closed" in detail or "reset" in detail or "eof" in detail:
            return "The database/pooler connection closed unexpectedly. Check that the Supabase project is active, use Session pooler port 5432, and retry the connection check."
        return (
            "PostgreSQL operation failed. Run --check-connection first; report this category and SQLSTATE "
            + (code or "unavailable")
            + ". Do not share DATABASE_URL."
        )
    if isinstance(exc, sqlite3.Error):
        return "The local SQLite snapshot could not be read or upgraded. Stop NORX and database viewers, and check the source file."
    if isinstance(exc, ValueError):
        # Only print known application-authored errors; never arbitrary values.
        known = {
            "Destination world is not empty; import refused",
            "Source database does not exist",
            "Import row count mismatch",
            "Database role needs CREATE privilege for NORX world schemas",
        }
        if str(exc) in known:
            return str(exc) + "."
    return "Migration could not finish. Check the source path, database configuration and whether workers are stopped."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.getenv("NORX_DB", "data/norx.sqlite3"))
    parser.add_argument("--world", choices=["all", *SCENARIOS], default="all")
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check-connection",
        action="store_true",
        help="Check PostgreSQL credentials/network without reading or importing saved worlds",
    )
    action.add_argument(
        "--apply",
        action="store_true",
        help="Import; default only previews source snapshots",
    )
    args = parser.parse_args()
    target = database_path()
    if not isinstance(target, PostgresTarget):
        parser.error("Set DATABASE_URL privately in your terminal first")
    if args.check_connection:
        connection_check(target)
        return
    if args.apply:
        connection_check(target)
    source = Path(args.source).expanduser()
    source = source if source.is_absolute() else PROJECT_ROOT / source
    chosen = SCENARIOS if args.world == "all" else [args.world]
    found = False
    for world in chosen:
        path = world_path(source, world)
        if not path.is_file():
            if args.world != "all":
                parser.error("Source database does not exist")
            continue
        found = True
        counts = import_world(path, world_path(target, world), args.apply)
        print(
            world
            + (": imported " if args.apply else ": preview ")
            + ", ".join(f"{n} {t}" for t, n in counts.items())
        )
    if not found:
        parser.error("No source databases found. Check --source")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = "Migration failed (" + type(exc).__name__ + "): " + safe_failure(exc)
        message += " Original SQLite data is unchanged."
        raise SystemExit(message) from None
