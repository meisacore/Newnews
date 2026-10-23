import tempfile
import random
from contextlib import contextmanager
import unittest
from unittest.mock import patch
from economy import Market, UNIT


class ScreenerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.market = Market(self.tmp.name + "/market.sqlite3")
        self.market.account("alice")
        self.market.account("bob")

    def trade(self, who, side, amount, ts, key):
        with patch("economy.time.time", return_value=ts):
            q = self.market.quote(
                who,
                "frog",
                side,
                budget=amount * UNIT if side == "buy" else None,
                qty=amount if side == "sell" else None,
            )
            self.market.execute(who, q["id"], key)

    def test_feed_query_count_stays_bounded_as_coins_grow(self):
        with self.market.transaction() as db:
            for i in range(30):
                db.execute("UPDATE meta SET value='0' WHERE key='next_launch_at'")
                self.market._launch_due(db, random.Random(i), 100000 + i * 60)
        queries = []
        original = self.market.connection

        @contextmanager
        def measured():
            with original() as db:
                db.set_trace_callback(queries.append)
                yield db

        with patch.object(self.market, "connection", measured):
            state = self.market.state("frog")
        self.assertEqual(state["total_coins"], 153)
        self.assertLess(len(queries), 30)

    def test_windows_count_actual_trades_and_keep_periods_distinct(self):
        now = 100000
        self.trade("alice", "buy", 200, now - 8 * 3600, "old")
        self.trade("alice", "buy", 100, now - 2 * 3600, "six")
        self.trade("bob", "buy", 50, now - 1800, "hour")
        self.trade("alice", "sell", 1, now - 60, "five")
        with patch("economy.time.time", return_value=now):
            s = self.market.state()
        coin = next(c for c in s["screener"] if c["id"] == "frog")
        self.assertEqual(
            [coin["windows"][w]["txns"] for w in ("5m", "1h", "6h", "24h")],
            [1, 2, 3, 4],
        )
        self.assertEqual(coin["windows"]["5m"]["buys"], 0)
        self.assertEqual(coin["windows"]["5m"]["sells"], 1)
        self.assertEqual(coin["windows"]["1h"]["traders"], 2)
        self.assertEqual(coin["windows"]["1h"]["buyers"], 1)
        for label, seconds in [
            ("5m", 300),
            ("1h", 3600),
            ("6h", 21600),
            ("24h", 86400),
        ]:
            with self.market.connection() as db:
                volume = (
                    db.execute(
                        "SELECT SUM(amount) FROM trades WHERE ts>=? AND ts<=?",
                        (now - seconds, now),
                    ).fetchone()[0]
                    / UNIT
                )
            self.assertEqual(s["market_totals"][label]["volume"], volume)
        empty = next(c for c in s["screener"] if c["id"] == "rocket")
        self.assertIsNone(empty["windows"]["5m"]["change"])

    def test_change_baseline_uses_trade_at_or_before_window_start(self):
        self.trade("alice", "buy", 100, 1000, "before")
        self.trade("bob", "buy", 100, 1500, "after")
        with patch("economy.time.time", return_value=1600):
            s = self.market.state()
        coin = next(c for c in s["screener"] if c["id"] == "frog")
        with self.market.connection() as db:
            baseline = db.execute("SELECT price FROM trades WHERE ts=1000").fetchone()[
                0
            ]
        self.assertAlmostEqual(
            coin["windows"]["5m"]["change"], (coin["price"] / baseline - 1) * 100
        )
