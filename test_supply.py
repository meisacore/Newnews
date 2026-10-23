import random
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from economy import Market, SUPPLY, UNIT


class SupplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "world.sqlite3"

    def test_new_world_and_future_launches_have_one_billion_tokens(self):
        m = Market(self.path)
        with m.transaction() as db:
            m._launch_due(db, random.Random(1), int(time.time()) + 61)
        with m.connection() as db:
            for c in db.execute("SELECT * FROM coins"):
                total = (
                    c["tokens"]
                    + db.execute(
                        "SELECT SUM(qty) FROM holdings WHERE coin=?", (c["id"],)
                    ).fetchone()[0]
                )
                self.assertEqual(total, 1000000000)
                self.assertGreaterEqual(c["tokens"], 50000000)
        self.assertTrue(all(c["total_supply"] == SUPPLY for c in m.state()["coins"]))

    def test_migration_preserves_values_cash_history_and_idempotency_once(self):
        with patch.multiple("economy", SUPPLY=1000000, TOKEN_SCALE=1):
            old = Market(self.path)
            old.account("alice")
            q = old.quote("alice", "frog", "buy", 100 * UNIT)
            result = old.execute("alice", q["id"], "done")
            pending = old.quote("alice", "frog", "buy", 50 * UNIT)
            account = old.account("alice")
            coin = next(c for c in old.state()["coins"] if c["id"] == "frog")
            candles = old.candles("frog")
            with old.connection() as db:
                cash = (
                    db.execute("SELECT SUM(cash) FROM accounts").fetchone()[0]
                    + db.execute("SELECT SUM(cash) FROM coins").fetchone()[0]
                )
        m = Market(self.path)
        after = m.account("alice")
        current = next(c for c in m.state()["coins"] if c["id"] == "frog")
        self.assertEqual(account["cash"], after["cash"])
        self.assertEqual(account["holdings"]["frog"] * 1000, after["holdings"]["frog"])
        self.assertAlmostEqual(
            account["holdings"]["frog"] * coin["price"],
            after["holdings"]["frog"] * current["price"],
        )
        self.assertAlmostEqual(coin["market_cap"], current["market_cap"])
        self.assertAlmostEqual(coin["fdv"], current["fdv"])
        migrated = m.candles("frog")
        self.assertAlmostEqual(candles[-1]["close"] / 1000, migrated[-1]["close"])
        self.assertEqual(candles[-1]["volume"], migrated[-1]["volume"])
        replay = m.execute("alice", q["id"], "done")
        self.assertEqual(replay["qty"], result["qty"] * 1000)
        self.assertEqual(replay["usd"], result["usd"])
        with self.assertRaisesRegex(ValueError, "expired"):
            m.execute("alice", pending["id"], "pending")
        Market(self.path)
        self.assertEqual(m.account("alice"), after)
        with m.connection() as db:
            self.assertEqual(
                cash,
                db.execute("SELECT SUM(cash) FROM accounts").fetchone()[0]
                + db.execute("SELECT SUM(cash) FROM coins").fetchone()[0],
            )
            self.assertEqual(db.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 1)

    def test_bad_supply_rolls_back_all_quantities(self):
        with patch.multiple("economy", SUPPLY=1000000, TOKEN_SCALE=1):
            m = Market(self.path)
        with m.transaction() as db:
            db.execute("UPDATE holdings SET qty=qty+1 WHERE coin='pebble'")
            before = [
                tuple(r)
                for r in db.execute("SELECT id,tokens,reference FROM coins ORDER BY id")
            ]
        with self.assertRaisesRegex(ValueError, "rolled back"):
            Market(self.path)
        with m.connection() as db:
            self.assertEqual(
                before,
                [
                    tuple(r)
                    for r in db.execute(
                        "SELECT id,tokens,reference FROM coins ORDER BY id"
                    )
                ],
            )
