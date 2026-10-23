import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from economy import Market, START, SUPPLY, UNIT


class EconomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "market.sqlite3"
        self.m = Market(self.path)
        self.m.account("alice")
        self.m.account("bob")

    def totals(self):
        with self.m.connection() as db:
            cash = (
                db.execute("SELECT SUM(cash) FROM accounts").fetchone()[0]
                + db.execute("SELECT SUM(cash) FROM coins").fetchone()[0]
            )
            supply = {
                r["id"]: r["tokens"]
                + db.execute(
                    "SELECT SUM(qty) FROM holdings WHERE coin=?", (r["id"],)
                ).fetchone()[0]
                for r in db.execute("SELECT * FROM coins")
            }
            return cash, supply

    def test_starting_grant_once_even_concurrently(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(self.m.account, ["new-user"] * 20))
        self.assertEqual(self.m.account("new-user")["cash"], 10000)

    def test_usd_budget_restart_and_idempotent_confirmation(self):
        q = self.m.quote("alice", "frog", "buy", 50 * UNIT)
        self.assertLessEqual(q["amount"], 50 * UNIT)
        result = self.m.execute("alice", q["id"], "request-123")
        self.assertEqual(result, self.m.execute("alice", q["id"], "request-123"))
        restored = Market(self.path).account("alice")
        self.assertEqual(restored["holdings"]["frog"], q["qty"])
        self.assertEqual(restored["cash"], (START - q["amount"]) / UNIT)
        self.assertEqual(len(restored["trades"]), 1)

    def test_quote_ownership_expiry_and_slippage(self):
        q = self.m.quote("alice", "frog", "buy", 50 * UNIT)
        with self.assertRaisesRegex(ValueError, "Unknown quote"):
            self.m.execute("bob", q["id"], "request-123")
        large = self.m.quote("bob", "frog", "buy", 3000 * UNIT)
        self.m.execute("bob", large["id"], "large-trade")
        before = self.m.account("alice")
        with self.assertRaisesRegex(ValueError, "Price moved"):
            self.m.execute("alice", q["id"], "request-123")
        self.assertEqual(before, self.m.account("alice"))
        q = self.m.quote("alice", "frog", "buy", 50 * UNIT)
        with self.m.transaction() as db:
            db.execute("UPDATE quotes SET expires=0 WHERE id=?", (q["id"],))
        with self.assertRaisesRegex(ValueError, "expired"):
            self.m.execute("alice", q["id"], "request-123")

    def test_sell_and_no_overspending(self):
        with self.assertRaises(ValueError):
            self.m.quote("alice", "frog", "sell", qty=1)
        with self.assertRaises(ValueError):
            self.m.quote("alice", "frog", "buy", START + 1)
        q = self.m.quote("alice", "frog", "buy", 50 * UNIT)
        self.m.execute("alice", q["id"], "buy-request")
        s = self.m.quote("alice", "frog", "sell", qty=q["qty"])
        self.m.execute("alice", s["id"], "sell-request")
        self.assertEqual(self.m.account("alice")["holdings"]["frog"], 0)
        self.assertLess(self.m.account("alice")["cash"], 10000)

    def test_conservation_and_agents_over_long_run(self):
        before = self.totals()
        for seed in range(300):
            self.m.tick(seed)
        self.assertEqual(before, self.totals())
        self.assertTrue(all(n == SUPPLY for n in self.totals()[1].values()))
        with self.m.connection() as db:
            self.assertGreater(
                db.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 100
            )
            self.assertGreater(
                db.execute("SELECT COUNT(*) FROM trades WHERE side='sell'").fetchone()[
                    0
                ],
                0,
            )
            self.assertGreaterEqual(
                db.execute("SELECT MIN(cash) FROM accounts").fetchone()[0], 0
            )

    def test_candles_and_market_cap(self):
        self.assertEqual(self.m.candles("frog"), [])
        q = self.m.quote("alice", "frog", "buy", 50 * UNIT)
        self.m.execute("alice", q["id"], "buy-request")
        candles = self.m.candles("frog")
        self.assertEqual(len(candles), 1)
        c = candles[0]
        self.assertEqual(c["volume"], q["amount"] / UNIT)
        self.assertLessEqual(c["low"], c["close"])
        self.assertGreaterEqual(c["high"], c["open"])
        state = self.m.state()["coins"][0]
        self.assertEqual(state["market_cap"], state["price"] * 100000000)
        self.assertEqual(state["fdv"], state["price"] * SUPPLY)
        with self.m.transaction() as db:
            db.execute("UPDATE trades SET ts=ts-180 WHERE coin=?", ("frog",))
        candles = self.m.candles("frog")
        self.assertGreaterEqual(len(candles), 3)
        self.assertEqual(candles[-1]["volume"], 0)
        self.assertEqual(candles[-1]["close"], candles[-2]["close"])


if __name__ == "__main__":
    unittest.main()
