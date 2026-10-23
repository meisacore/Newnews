"""Integration tests against disposable schemas in a real PostgreSQL database.
Run with NORX_TEST_POSTGRES_URL; never point this at a live user database.
"""

import os
import time
import tempfile
import unittest
import uuid
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from economy import Market, SUPPLY, UNIT
from migrate_storage import import_world, migration_connection
from paths import world_path
from storage import PostgresTarget, postgres_worker_lock, _pools
from filelock import Timeout


@unittest.skipUnless(
    os.getenv("NORX_TEST_POSTGRES_URL"), "PostgreSQL integration URL not set"
)
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.target = PostgresTarget(
            os.environ["NORX_TEST_POSTGRES_URL"],
            "norx_test_" + uuid.uuid4().hex[:12] + "_balanced",
        )
        self.targets = [self.target]
        self.addCleanup(self.cleanup_database)

    def cleanup_database(self):
        import psycopg
        from psycopg import sql

        for target in self.targets:
            pool = _pools.pop(target, None)
            if pool:
                pool.close()
            with psycopg.connect(target.url, autocommit=True) as db:
                db.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(target.schema)
                    )
                )

    def totals(self, market):
        with market.connection() as db:
            cash = (
                db.execute("SELECT SUM(cash) FROM accounts").fetchone()[0]
                + db.execute("SELECT SUM(cash) FROM coins").fetchone()[0]
            )
            supply = {
                r["id"]: r["tokens"]
                + db.execute(
                    "SELECT COALESCE(SUM(qty),0) FROM holdings WHERE coin=?", (r["id"],)
                ).fetchone()[0]
                for r in db.execute("SELECT id,tokens FROM coins")
            }
            return cash, supply

    def test_ledger_conservation_candles_and_restart(self):
        market = Market(self.target)
        market.account("did:privy:player")
        before = self.totals(market)
        quote = market.quote("did:privy:player", "frog", "buy", 50 * UNIT)
        result = market.execute("did:privy:player", quote["id"], "pg-trade-request")
        for seed in range(30):
            market.tick(seed=seed, now=1000)
        self.assertEqual(before, self.totals(market))
        self.assertTrue(all(v == SUPPLY for v in before[1].values()))
        self.assertTrue(market.candles("frog"))
        self.assertEqual(market.state("frog")["api_version"], 6)
        self.assertEqual(
            Market(self.target).account("did:privy:player")["holdings"]["frog"],
            result["qty"],
        )
        self.assertEqual(
            market.execute("did:privy:player", quote["id"], "pg-trade-request"), result
        )

    def test_concurrent_grant_and_execution_are_idempotent(self):
        market = Market(self.target)
        with ThreadPoolExecutor(max_workers=4) as executor:
            accounts = list(executor.map(market.account, ["did:privy:player"] * 8))
        self.assertTrue(all(a["cash"] == 10000 for a in accounts))
        quote = market.quote("did:privy:player", "frog", "buy", 50 * UNIT)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(
                    lambda _: market.execute(
                        "did:privy:player", quote["id"], "concurrent-order"
                    ),
                    range(8),
                )
            )
        self.assertTrue(all(r == results[0] for r in results))
        with market.connection() as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM trades WHERE account=?", ("did:privy:player",)
                ).fetchone()[0],
                1,
            )
        self.assertAlmostEqual(
            market.account("did:privy:player")["cash"], 9950, places=3
        )

    def test_worker_ownership_and_scenarios(self):
        market = Market(self.target)
        other = world_path(self.target, "bull")
        self.targets.append(other)
        bull = Market(other, scenario="bull")
        market.account("did:privy:player")
        q = market.quote("did:privy:player", "frog", "buy", 50 * UNIT)
        market.execute("did:privy:player", q["id"], "balanced-buy")
        self.assertEqual(bull.account("did:privy:player")["cash"], 10000)
        with self.assertRaises(ValueError):
            bull.execute("did:privy:player", q["id"], "wrong-world")
        with postgres_worker_lock(self.target):
            with self.assertRaises(Timeout):
                with postgres_worker_lock(self.target):
                    self.fail("Two owners")
            with postgres_worker_lock(other):
                pass
        with postgres_worker_lock(self.target):
            pass

    def test_snapshot_import_preserves_data_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "world.sqlite3"
            local = Market(source)
            local.account("did:privy:player")
            q = local.quote("did:privy:player", "frog", "buy", 50 * UNIT)
            result = local.execute("did:privy:player", q["id"], "original-buy")
            pending = local.quote("did:privy:player", "frog", "buy", 50 * UNIT)
            before = local.account("did:privy:player")
            preview = import_world(source, self.target)
            self.assertEqual(preview["trades"], 1)
            self.assertEqual(preview, import_world(source, self.target, apply=True))
            migrated = Market(self.target)
            self.assertEqual(before, migrated.account("did:privy:player"))
            self.assertEqual(self.totals(local), self.totals(migrated))
            self.assertEqual(
                result, migrated.execute("did:privy:player", q["id"], "original-buy")
            )
            with self.assertRaises(ValueError):
                migrated.execute("did:privy:player", pending["id"], "pending-stale")
            q2 = migrated.quote("did:privy:player", "frog", "sell", qty=result["qty"])
            second = migrated.execute("did:privy:player", q2["id"], "after-import")
            self.assertGreater(second["trade_id"], result["trade_id"])
            with self.assertRaises(ValueError):
                import_world(source, self.target, apply=True)
            self.assertEqual(before, local.account("did:privy:player"))

    def test_worker_takes_over_and_launches(self):
        from worker import SimulationRunner

        market = Market(self.target)
        with market.transaction() as db:
            db.execute("UPDATE meta SET value='0' WHERE key='next_launch_at'")
        runner = SimulationRunner(self.target, interval=0.05)
        try:
            with postgres_worker_lock(self.target):
                runner.start()
                time.sleep(0.15)
                self.assertFalse(market.state()["simulation"]["running"])
            deadline = time.monotonic() + 10
            while True:
                state = market.state()
                if state["simulation"]["running"] and state["total_coins"] == 8:
                    break
                if time.monotonic() > deadline:
                    self.fail("PostgreSQL worker did not take ownership and launch")
                time.sleep(0.05)
        finally:
            runner.stop()
        with postgres_worker_lock(self.target):
            pass

    def test_failed_import_rolls_back_and_can_retry(self):
        from storage import PostgresConnection, connection

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.sqlite3"
            Market(source).account("did:privy:saved")
            original = PostgresConnection.execute

            def fail_after_copy(db, query, params=()):
                if query.startswith("UPDATE quotes SET expires"):
                    raise ValueError("injected failure")
                return original(db, query, params)

            with (
                patch.object(PostgresConnection, "execute", fail_after_copy),
                self.assertRaises(ValueError),
            ):
                import_world(source, self.target, apply=True)
            with connection(self.target) as db:
                count = db.raw.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s",
                    (self.target.schema,),
                ).fetchone()[0]
                self.assertEqual(count, 0)
            import_world(source, self.target, apply=True)
            self.assertEqual(
                Market(self.target).account("did:privy:saved")["cash"], 10000
            )

    def test_bulk_import_timeout_is_separate_and_connection_always_closes(self):
        import psycopg
        from storage import connection

        self.assertNotIn(self.target, _pools)
        with migration_connection(self.target) as db:
            raw = db.raw
            self.assertEqual(
                raw.execute("SHOW statement_timeout").fetchone()[0], "15min"
            )
            raw.execute("SELECT pg_sleep(0.06)")
        self.assertTrue(raw.closed)
        self.assertNotIn(self.target, _pools)
        with self.assertRaises(psycopg.errors.QueryCanceled):
            with migration_connection(self.target) as db:
                canceled_raw = db.raw
                db.raw.execute("SET LOCAL statement_timeout TO '20ms'")
                db.raw.execute("SELECT pg_sleep(0.08)")
        self.assertTrue(canceled_raw.closed)
        self.assertNotIn(self.target, _pools)
        # Neither successful uncommitted work nor cancellation leaves partial
        # schemas. The normal API connection keeps its short request timeout.
        Market(self.target)
        with connection(self.target) as db:
            self.assertEqual(
                db.raw.execute("SHOW statement_timeout").fetchone()[0], "30s"
            )

    def test_saved_market_startup_and_feed_have_bounded_round_trips(self):
        from storage import PostgresConnection

        market = Market(self.target)
        with market.transaction() as db:
            for i in range(30):
                db.execute("UPDATE meta SET value='0' WHERE key='next_launch_at'")
                market._launch_due(db, random.Random(i), 100000 + i * 60)
        queries = []
        original = PostgresConnection.execute

        def measured(db, query, params=()):
            queries.append(query)
            return original(db, query, params)

        with patch.object(PostgresConnection, "execute", measured):
            reopened = Market(self.target)
        profile_inserts = [
            q for q in queries if "INSERT" in q and "agent_personas" in q
        ]
        self.assertLessEqual(len(profile_inserts), 6)
        queries.clear()
        with patch.object(PostgresConnection, "execute", measured):
            state = reopened.state("frog")
        self.assertEqual(state["total_coins"], 153)
        self.assertLess(len(queries), 30)

    def test_api_uses_postgres_and_private_rls_tables(self):
        from fastapi.testclient import TestClient
        import server

        market = Market(self.target)
        with patch.object(server, "market", market):
            server.app.dependency_overrides[server.identity] = lambda: "did:privy:api"
            try:
                client = TestClient(server.app)
                self.assertEqual(client.get("/api/me").status_code, 200)
                quote = client.post(
                    "/api/quote",
                    json={"coin": "frog", "side": "buy", "budget": 50 * UNIT},
                ).json()
                self.assertEqual(
                    client.post(
                        "/api/trade",
                        json={"quote_id": quote["id"], "request_id": "pg-api-request"},
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    client.get("/api/state?selected=frog").status_code, 200
                )
                self.assertEqual(client.get("/api/candles/frog").status_code, 200)
            finally:
                server.app.dependency_overrides.clear()
        with market.connection() as db:
            rows = db.raw.execute(
                "SELECT relrowsecurity FROM pg_class JOIN pg_namespace n ON n.oid=relnamespace WHERE n.nspname=%s AND relkind='r'",
                (self.target.schema,),
            ).fetchall()
            self.assertTrue(rows)
            self.assertTrue(all(r[0] for r in rows))


if __name__ == "__main__":
    unittest.main()
