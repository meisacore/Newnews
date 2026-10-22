import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from economy import LAUNCH_BATCH, Market, SUPPLY, UNIT


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = patch("economy.time.time", return_value=1000)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.path = Path(self.tmp.name) / "launch.sqlite3"
        self.market = Market(self.path)

    def total_cash(self):
        with self.market.connection() as db:
            return (
                db.execute("SELECT SUM(cash) FROM accounts").fetchone()[0]
                + db.execute("SELECT SUM(cash) FROM coins").fetchone()[0]
            )

    def test_exactly_five_at_boundary_and_no_duplicate_on_restart(self):
        self.market.tick(seed=1, now=1059)
        self.assertEqual(self.market.state()["total_coins"], 3)
        before = self.total_cash()
        self.market.tick(seed=2, now=1060)
        self.assertEqual(self.market.state()["total_coins"], 3 + LAUNCH_BATCH)
        with self.market.connection() as db:
            seed = db.execute(
                "SELECT SUM(seed_cash) FROM launches WHERE coin LIKE 'coin-%'"
            ).fetchone()[0]
            for row in db.execute("SELECT id,tokens FROM coins"):
                holdings = db.execute(
                    "SELECT SUM(qty) FROM holdings WHERE coin=?", (row["id"],)
                ).fetchone()[0]
                self.assertEqual(row["tokens"] + holdings, SUPPLY)
        self.assertEqual(self.total_cash() - before, seed)
        restored = Market(self.path)
        restored.tick(seed=3, now=1060)
        self.assertEqual(restored.state()["total_coins"], 8)
        restored.tick(seed=4, now=1120)
        self.assertEqual(restored.state()["total_coins"], 13)

    def test_concurrent_ticks_launch_one_batch_and_downtime_no_flood(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda seed: self.market.tick(seed=seed, now=1060), range(4)))
        self.assertEqual(self.market.state()["total_coins"], 8)
        self.market.tick(seed=9, now=100000)
        state = self.market.state()
        self.assertEqual(state["total_coins"], 13)
        self.assertEqual(state["next_launch_at"], 100060)
        new = [c for c in state["coins"] if c["id"].startswith("coin-")]
        self.assertEqual(len({c["symbol"] for c in new}), 10)
        self.assertGreater(len({c["pool_usd"] for c in new}), 1)

    def test_new_coin_trades_persists_and_builds_its_own_chart(self):
        self.market.tick(seed=22, now=1060)
        coin = next(
            c for c in self.market.state()["coins"] if c["id"].startswith("coin-")
        )
        self.market.account("alice")
        quote = self.market.quote("alice", coin["id"], "buy", 50 * UNIT)
        self.market.execute("alice", quote["id"], "new-coin-buy")
        restored = Market(self.path)
        self.assertEqual(
            restored.account("alice")["holdings"][coin["id"]], quote["qty"]
        )
        self.assertTrue(restored.candles(coin["id"]))
        position = restored.account("alice")["positions"][0]
        self.assertEqual(position["id"], coin["id"])
        self.assertEqual(position["qty"], quote["qty"])

    def test_pulse_stages_follow_real_volume(self):
        self.market.account("alice")

        def frog():
            return next(c for c in self.market.state()["coins"] if c["id"] == "frog")

        self.assertEqual(frog()["stage"], "new")
        quote = self.market.quote("alice", "frog", "buy", 7200 * UNIT)
        self.market.execute("alice", quote["id"], "first-buy")
        sell = self.market.quote("alice", "frog", "sell", qty=quote["qty"])
        self.market.execute("alice", sell["id"], "first-sell")
        self.assertEqual(frog()["stage"], "stretch")
        quote = self.market.quote("alice", "frog", "buy", 4000 * UNIT)
        self.market.execute("alice", quote["id"], "second-buy")
        sell = self.market.quote("alice", "frog", "sell", qty=quote["qty"])
        self.market.execute("alice", sell["id"], "second-sell")
        self.assertEqual(frog()["stage"], "migrated")
        self.assertEqual(frog()["progress"], 100)

    def test_additive_upgrade_preserves_existing_world(self):
        self.market.account("alice")
        q = self.market.quote("alice", "frog", "buy", 50 * UNIT)
        self.market.execute("alice", q["id"], "pre-upgrade-buy")
        before = self.market.account("alice")
        cash = self.total_cash()
        with self.market.transaction() as db:
            db.execute("DROP TABLE launches")
            db.execute(
                "DELETE FROM meta WHERE key IN ('next_launch_at','launch_sequence')"
            )
        restored = Market(self.path)
        self.assertEqual(restored.account("alice"), before)
        self.assertEqual(self.total_cash(), cash)
        self.assertEqual(restored.state()["total_coins"], 3)
        self.assertEqual(restored.state()["next_launch_at"], 1060)

    def test_feed_bounded_but_old_selected_coin_and_position_accessible(self):
        self.market.account("alice")
        q = self.market.quote("alice", "frog", "buy", 50 * UNIT)
        self.market.execute("alice", q["id"], "old-coin-buy")
        with self.market.transaction() as db:
            for n in range(14):
                self.market._launch_due(
                    db, __import__("random").Random(n), 1060 + n * 60
                )
        self.assertEqual(self.market.state()["total_coins"], 73)
        self.assertLessEqual(len(self.market.state()["coins"]), 60)
        self.assertIn(
            "frog", [c["id"] for c in self.market.state(selected="frog")["coins"]]
        )
        self.assertEqual(self.market.account("alice")["positions"][0]["id"], "frog")


if __name__ == "__main__":
    unittest.main()
