"""Cloudflare integration checks in disposable schemas, never live NORX worlds.

NORX_TEST_POSTGRES_URL must name a disposable PostgreSQL test database.
"""

import os
import random
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql

from cloudflare.prepare import prepare
from economy import SUPPLY, UNIT, Market
from paths import database_path
from scenarios import SCENARIOS
from storage import _pools


def run():
    url = os.environ.get("NORX_TEST_POSTGRES_URL")
    if not url:
        raise SystemExit(
            "Set NORX_TEST_POSTGRES_URL to a disposable PostgreSQL database"
        )
    prefix = "norx_cf_test_" + uuid.uuid4().hex[:10] + "_"
    try:
        with patch.dict(
            os.environ, {"DATABASE_URL": url, "NORX_PG_SCHEMA_PREFIX": prefix}
        ):
            prepare("cloudflare")
            market = Market(database_path())
            # Python workers must not advance a world after cutover.
            before = market.state()["total_coins"]
            market.tick(seed=42, now=10**10)
            assert market.state()["total_coins"] == before
            rng = random.Random(91)
            with psycopg.connect(url) as db:
                db.execute(
                    sql.SQL("SET search_path TO {}").format(
                        sql.Identifier(prefix + "balanced")
                    )
                )
                # Exact integer parity, including products beyond JS's safe range.
                for _ in range(200):
                    c = {
                        "tokens": rng.randint(100, SUPPLY),
                        "cash": rng.randint(1, 10**14),
                    }
                    qty = rng.randint(1, c["tokens"] - 1)
                    for side in ("buy", "sell"):
                        paid = db.execute(
                            "SELECT norx_amount(%s,%s,%s,%s)",
                            (c["tokens"], c["cash"], side, qty),
                        ).fetchone()[0]
                        assert paid == market.amount(c, side, qty)
                    budget = rng.randint(0, c["cash"])
                    q = db.execute(
                        "SELECT norx_quantity(%s,%s,%s)",
                        (c["tokens"], c["cash"], budget),
                    ).fetchone()[0]
                    assert q == market.quantity(c, budget)
            # Completed Python quotes remain idempotent after moving to Workers.
            market.account("did:privy:pre-cutover")
            quote = market.quote("did:privy:pre-cutover", "rocket", "buy", 25 * UNIT)
            receipt = market.execute(
                "did:privy:pre-cutover", quote["id"], "pre-cutover-request"
            )
            with psycopg.connect(url) as db:
                db.execute(
                    sql.SQL("SET search_path TO {}").format(
                        sql.Identifier(prefix + "balanced")
                    )
                )
                replay = db.execute(
                    "SELECT norx_execute(%s,%s,%s)",
                    ("did:privy:pre-cutover", quote["id"], "pre-cutover-request"),
                ).fetchone()[0]
                assert replay == receipt
            # A fresh quote expires and an adverse moved price cannot spend money.
            with psycopg.connect(url) as db:
                db.execute(
                    sql.SQL("SET search_path TO {}").format(
                        sql.Identifier(prefix + "balanced")
                    )
                )
                db.execute(
                    "SELECT norx_quote(%s,'frog','buy',50000000,NULL,'expired')",
                    ("did:privy:pre-cutover",),
                )
                db.execute("UPDATE quotes SET expires=0 WHERE id='expired'")
            try:
                with psycopg.connect(url) as db:
                    db.execute(
                        sql.SQL("SET search_path TO {}").format(
                            sql.Identifier(prefix + "balanced")
                        )
                    )
                    db.execute(
                        "SELECT norx_execute(%s,'expired','expired-request')",
                        ("did:privy:pre-cutover",),
                    )
            except psycopg.errors.RaiseException as exc:
                assert "expired" in str(exc)
            else:
                raise AssertionError("Expired quote executed")
            result = subprocess.run(
                [
                    "node",
                    "--test",
                    "cloudflare/test/auth.test.js",
                    "cloudflare/test/runtime.test.js",
                ],
                check=False,
                env={
                    **os.environ,
                    "NORX_TEST_POSTGRES_URL": url,
                    "NORX_TEST_PG_SCHEMA_PREFIX": prefix,
                },
            )
            if result.returncode:
                raise SystemExit(result.returncode)
            print(
                "Cloudflare integer parity, Python receipt continuity, cutover guard and PostgreSQL API checks passed"
            )
    finally:
        for world in SCENARIOS:
            for target, pool in list(_pools.items()):
                if target.schema == prefix + world:
                    pool.close()
                    _pools.pop(target, None)
            with psycopg.connect(url, autocommit=True) as db:
                db.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(prefix + world)
                    )
                )


if __name__ == "__main__":
    run()
