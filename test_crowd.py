import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from economy import Market, UNIT, TRADER_POPULATION, DECISIONS_PER_TICK


class CrowdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "world.sqlite3"
        self.market = Market(self.path)

    def test_upgrade_from_36_traders_retains_accounts_and_funds_new_traders_once(self):
        account = self.market.account("alice")
        with self.market.transaction() as db:
            db.execute("DELETE FROM accounts WHERE id LIKE 'agent-crowd-%'")
            db.execute("DELETE FROM agent_personas WHERE account LIKE 'agent-crowd-%'")
            db.execute("DELETE FROM agent_grants WHERE account LIKE 'agent-crowd-%'")
            db.execute("UPDATE accounts SET cash=123456789 WHERE id='agent-01'")
        upgraded = Market(self.path)
        self.assertEqual(len(upgraded.state()["agents"]), TRADER_POPULATION)
        self.assertEqual(upgraded.account("alice"), account)
        with upgraded.transaction() as db:
            self.assertEqual(
                db.execute("SELECT cash FROM accounts WHERE id='agent-01'").fetchone()[
                    0
                ],
                123456789,
            )
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(DISTINCT persona) FROM agent_personas"
                ).fetchone()[0],
                7,
            )
            db.execute("UPDATE accounts SET cash=17 WHERE id='agent-crowd-00001'")
            before = [
                tuple(r)
                for r in db.execute("SELECT * FROM agent_grants ORDER BY account")
            ]
        Market(self.path)
        with upgraded.connection() as db:
            self.assertEqual(
                db.execute(
                    "SELECT cash FROM accounts WHERE id='agent-crowd-00001'"
                ).fetchone()[0],
                17,
            )
            self.assertEqual(
                before,
                [
                    tuple(r)
                    for r in db.execute("SELECT * FROM agent_grants ORDER BY account")
                ],
            )

    def test_cohort_is_bounded_and_draws_from_many_distinct_traders(self):
        identities = set()
        with patch.object(self.market, "_agent_decision", return_value=False) as decide:
            for seed in range(40):
                decide.reset_mock()
                self.market.tick(seed=seed)
                ids = [call.args[1]["id"] for call in decide.call_args_list]
                self.assertLessEqual(len(ids), DECISIONS_PER_TICK)
                self.assertEqual(len(ids), len(set(ids)))
                identities.update(ids)
        self.assertGreater(len(identities), 500)

    def test_trending_uses_recent_buys_and_expires_without_new_buys(self):
        self.market.account("buyer")
        with patch("economy.time.time", return_value=1000):
            q = self.market.quote("buyer", "frog", "buy", 100 * UNIT)
            self.market.execute("buyer", q["id"], "buy-one")
            s = self.market.state()
        self.assertEqual(s["trending"][0]["id"], "frog")
        self.assertEqual(s["trending"][0]["buyers_5m"], 1)
        self.assertEqual(s["trending"][0]["buys_5m"], 1)
        self.assertGreater(s["trending"][0]["buy_usd_5m"], 0)
        with patch("economy.time.time", return_value=1301):
            self.assertEqual(self.market.state()["trending"], [])

    def test_trending_counts_buyers_once_and_does_not_call_sell_only_flow_hot(self):
        self.market.account("alice")
        self.market.account("bob")

        def execute(who, coin, side, amount, key):
            q = self.market.quote(
                who,
                coin,
                side,
                amount if side == "buy" else None,
                qty=amount if side == "sell" else None,
            )
            self.market.execute(who, q["id"], key)

        with patch("economy.time.time", return_value=500):
            execute("alice", "rocket", "buy", 100 * UNIT, "old-buy")
        with patch("economy.time.time", return_value=1000):
            execute("alice", "rocket", "sell", 1, "recent-sell")
            execute("alice", "frog", "buy", 100 * UNIT, "first-buy")
            execute("alice", "frog", "buy", 100 * UNIT, "second-buy")
            execute("bob", "frog", "buy", 100 * UNIT, "third-buy")
            row = self.market.state()["trending"][0]
        self.assertEqual(row["id"], "frog")
        self.assertEqual(row["buyers_5m"], 2)
        self.assertEqual(row["buys_5m"], 3)
        self.assertEqual(row["sells_5m"], 0)
        with self.market.connection() as db:
            expected = (
                db.execute(
                    "SELECT SUM(amount) FROM trades WHERE coin='frog' AND side='buy'"
                ).fetchone()[0]
                / UNIT
            )
        self.assertEqual(row["buy_usd_5m"], expected)

    def test_old_hot_market_is_retained_outside_the_recent_launch_feed(self):
        with self.market.transaction() as db:
            db.execute("UPDATE launches SET created_at=0")
            db.execute("UPDATE meta SET value='0' WHERE key='next_launch_at'")
            for i in range(15):
                self.market._launch_due(
                    db, __import__("random").Random(i), 100000 + i * 60
                )
        self.market.account("buyer")
        q = self.market.quote("buyer", "frog", "buy", 100 * UNIT)
        self.market.execute("buyer", q["id"], "old-market")
        s = self.market.state()
        self.assertIn("frog", [c["id"] for c in s["trending"]])
        self.assertNotIn("frog", [c["id"] for c in s["coins"]])
        self.assertFalse(next(c for c in s["trending"] if c["id"] == "frog")["in_feed"])
