"""Add the Cloudflare runtime to existing PostgreSQL worlds without reimporting.

Run from the repository root: .venv/Scripts/python cloudflare/prepare.py
Stop Python API/worker processes first. DATABASE_URL is read from the environment.
This intentionally never prints the URL, password or private user records.
"""

import argparse
import sys
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from filelock import Timeout
from psycopg import sql

from economy import Market
from migrate_storage import safe_failure
from paths import database_path, world_path
from scenarios import SCENARIOS
from storage import PostgresTarget, _pools, postgres_worker_lock


def prepare(mode=None):
    target = database_path()
    if not isinstance(target, PostgresTarget):
        raise TypeError(
            "Set DATABASE_URL to your existing Supabase session pooler URL first"
        )
    script = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with ExitStack() as owners:
        # Refuse cutover while any old Python simulation owns a world.
        for world in SCENARIOS:
            owners.enter_context(postgres_worker_lock(world_path(target, world)))
        for world in SCENARIOS:
            dest = world_path(target, world)
            # Existing ledger is retained; missing worlds get normal finite grants.
            try:
                Market(dest, scenario=world)
            finally:
                pool = _pools.pop(dest, None)
                if pool:
                    pool.close()
            with psycopg.connect(dest.url) as db:
                db.execute("SET LOCAL statement_timeout='60s'")
                db.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("norx-write-" + dest.schema,),
                )
                db.execute(
                    sql.SQL("SET LOCAL search_path TO {} ").format(
                        sql.Identifier(dest.schema)
                    )
                )
                db.execute(script, prepare=False)
                if mode:
                    db.execute(
                        "INSERT INTO meta VALUES('simulation_engine',%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (mode,),
                    )
                    db.execute(
                        "UPDATE cloud_runtime SET active_until=0,next_batch_at=0,snapshot=NULL,snapshot_at=0 WHERE id=1"
                    )
            print(
                f"{world}: Cloudflare functions ready; saved ledger retained",
                flush=True,
            )
    print(
        "Ready. Engine: "
        + (mode or "unchanged (use --activate for Cloudflare cutover)")
    )


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument(
            "--activate",
            action="store_true",
            help="Stop Python simulation and switch these worlds to Cloudflare",
        )
        modes.add_argument(
            "--deactivate",
            action="store_true",
            help="Return to the Python simulation without changing ledger data",
        )
        args = parser.parse_args()
        prepare(
            "cloudflare" if args.activate else "python" if args.deactivate else None
        )
    except Exception as exc:  # noqa: BLE001 -- redact database credentials in CLI errors
        # Full database exceptions may contain connection strings or SQL parameters.
        if isinstance(exc, Timeout):
            detail = "A Python simulation still owns a world. Stop the API and all worker.py processes, then retry."
        elif isinstance(exc, psycopg.OperationalError):
            detail = safe_failure(exc)
        elif isinstance(exc, psycopg.Error):
            detail = (
                "Database setup failed (SQLSTATE "
                + (exc.sqlstate or "unavailable")
                + "). Update the complete project and check database permissions."
            )
        else:
            detail = "Set DATABASE_URL to your working Supabase session pooler URL and stop Python workers."
        print(f"Preparation failed ({type(exc).__name__}): {detail}", file=sys.stderr)
        sys.exit(1)
