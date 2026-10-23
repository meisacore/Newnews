"""Preview or import SQLite snapshots into empty PostgreSQL world schemas.

Stop NORX and all workers first. DATABASE_URL stays in the environment, never in
command arguments. Original files are read-only; imports are atomic per world.
"""

import argparse
import os
import sqlite3
import tempfile
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
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
            with sqlite3.connect(snapshot) as copied:
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.getenv("NORX_DB", "data/norx.sqlite3"))
    parser.add_argument("--world", choices=["all", *SCENARIOS], default="all")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Import; default only previews source snapshots",
    )
    args = parser.parse_args()
    target = database_path()
    if not isinstance(target, PostgresTarget):
        parser.error("Set DATABASE_URL privately in your terminal first")
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
        # Never echo a connection string, password, token, or a driver traceback.
        raise SystemExit(
            "Migration failed ("
            + type(exc).__name__
            + "). Destination must be empty and reachable; originals are unchanged. Check database settings and stop workers before retrying."
        ) from None
