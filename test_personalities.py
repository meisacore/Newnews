import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from economy import Market, UNIT, TRADER_POPULATION
from personalities import PERSONALITIES, WEALTHY_ENTRANTS


def eager_rng(choice=0):
    rng = Mock()
    rng.random.return_value = choice
    rng.uniform.side_effect = lambda low, high: high
    rng.gauss.return_value = 0
    rng.choice.return_value = 1
    return rng


class PersonalityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        clock = patch("economy.time.time", return_value=1000)
        clock.start()
        self.addCleanup(clock.stop)
        self.path = Path(self.tmp.name) / "agents.sqlite3"
        self.market = Market(self.path)

    def agent(self, db, identity):
        return db.execute(
            "SELECT a.*,p.* FROM accounts a JOIN agent_personas p ON a.id=p.account WHERE a.id=?",
            (identity,),
        ).fetchone()

    def test_wealthy_impulsive_buy_is_large_but_cash_and_liquidity_are_finite(self):
        with self.market.transaction() as db:
            agent = self.agent(db, "agent-whale-03")
            db.execute(
                "UPDATE coins SET cash=cash*10,reference=reference*10 WHERE id='frog'"
            )
            before = agent["cash"]
            self.assertTrue(self.market._agent_decision(db, agent, "frog", eager_rng()))
            trade = db.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertGreater(trade["amount"], 10000 * UNIT)
            self.assertLess(trade["amount"], before)
            self.assertGreater(
                db.execute("SELECT tokens FROM coins WHERE id='frog'").fetchone()[0], 0
            )
            self.assertIn("Reckless whale", trade["reason"])
            self.assertAlmostEqual(
                db.execute(
                    "SELECT cash FROM accounts WHERE id='agent-whale-03'"
                ).fetchone()[0]
                + trade["amount"],
                before,
            )
        self.assertTrue(self.market.state()["large_trades"])

    def test_disciplined_whale_refuses_overpriced_market_while_reckless_one_buys(self):
        with self.market.transaction() as db:
            db.execute("UPDATE coins SET reference=.00001 WHERE id='frog'")
            self.assertFalse(
                self.market._agent_decision(
                    db, self.agent(db, "agent-whale-01"), "frog", eager_rng()
                )
            )
            self.assertTrue(
                self.market._agent_decision(
                    db, self.agent(db, "agent-whale-03"), "frog", eager_rng()
                )
            )

    def test_disciplined_whale_sizes_down_for_actual_execution_cost(self):
        with self.market.transaction() as db:
            db.execute("UPDATE coins SET reference=.001 WHERE id='frog'")
            coin = db.execute("SELECT * FROM coins WHERE id='frog'").fetchone()
            spot = coin["cash"] / coin["tokens"]
            self.assertTrue(
                self.market._agent_decision(
                    db, self.agent(db, "agent-whale-01"), "frog", eager_rng()
                )
            )
            trade = db.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertLessEqual(
                trade["amount"] / trade["qty"],
                spot * (1 + PERSONALITIES["patient_value"].impact_bps / 10000),
            )
            self.assertLessEqual(trade["amount"] / trade["qty"], UNIT * 0.001 * 0.995)

    def test_reckless_overpayment_can_transfer_money_to_other_traders_and_lose(self):
        self.market.account("alice")
        q = self.market.quote("alice", "frog", "buy", 5000 * UNIT)
        self.market.execute("alice", q["id"], "early-entry")
        with self.market.transaction() as db:
            self.market._agent_decision(
                db, self.agent(db, "agent-whale-03"), "frog", eager_rng()
            )
        sell = self.market.quote("alice", "frog", "sell", qty=q["qty"])
        self.market.execute("alice", sell["id"], "take-profit")
        with self.market.transaction() as db:
            self.assertTrue(
                self.market._agent_decision(
                    db, self.agent(db, "agent-whale-03"), "frog", eager_rng(0.7)
                )
            )
            remaining = db.execute(
                "SELECT cash FROM accounts WHERE id='agent-whale-03'"
            ).fetchone()[0]
            self.assertGreater(1_500_000 * UNIT - remaining, 1 * UNIT)
            self.assertEqual(
                db.execute(
                    "SELECT qty FROM holdings WHERE account='agent-whale-03' AND coin='frog'"
                ).fetchone()[0],
                0,
            )
        self.assertGreater(self.market.account("alice")["cash"], 10000)
        Market(self.path)
        with self.market.connection() as db:
            self.assertEqual(
                db.execute(
                    "SELECT cash FROM accounts WHERE id='agent-whale-03'"
                ).fetchone()[0],
                remaining,
            )
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM agent_grants WHERE account LIKE 'agent-whale-%'"
                ).fetchone()[0],
                len(WEALTHY_ENTRANTS),
            )

    def test_existing_accounts_preserved_and_new_grants_issued_only_once(self):
        self.market.account("alice")
        with self.market.transaction() as db:
            for identity, _, _, _ in WEALTHY_ENTRANTS:
                db.execute("DELETE FROM accounts WHERE id=?", (identity,))
                db.execute("DELETE FROM agent_personas WHERE account=?", (identity,))
                db.execute("DELETE FROM agent_grants WHERE account=?", (identity,))
            before = {
                r["id"]: r["cash"] for r in db.execute("SELECT id,cash FROM accounts")
            }
        restored = Market(self.path)
        with restored.connection() as db:
            for identity, cash in before.items():
                self.assertEqual(
                    db.execute(
                        "SELECT cash FROM accounts WHERE id=?", (identity,)
                    ).fetchone()[0],
                    cash,
                )
            after = {
                r["id"]: r["cash"] for r in db.execute("SELECT id,cash FROM accounts")
            }
        Market(self.path)
        with restored.connection() as db:
            self.assertEqual(
                after,
                {
                    r["id"]: r["cash"]
                    for r in db.execute("SELECT id,cash FROM accounts")
                },
            )

    def test_global_cooldown_and_mixed_population_produce_large_and_small_buys(self):
        self.market.tick(seed=0, now=1000)
        with self.market.connection() as db:
            self.assertLessEqual(
                db.execute(
                    "SELECT COALESCE(MAX(n),0) FROM (SELECT COUNT(*) n FROM trades GROUP BY account)"
                ).fetchone()[0],
                1,
            )
        for seed in range(1, 120):
            self.market.tick(seed=seed, now=1000)
        with self.market.connection() as db:
            sizes = db.execute(
                "SELECT MIN(amount),MAX(amount) FROM trades WHERE side='buy'"
            ).fetchone()
            self.assertLess(sizes[0], 100 * UNIT)
            self.assertGreater(sizes[1], 5000 * UNIT)
            self.assertGreaterEqual(
                db.execute("SELECT MIN(cash) FROM accounts").fetchone()[0], 0
            )
        self.assertEqual(len(self.market.state()["agents"]), TRADER_POPULATION)
        self.assertTrue(
            any(
                a["disciplined"] and a["starting_cash"]
                for a in self.market.state()["agents"]
            )
        )
        self.assertTrue(
            any(
                not a["disciplined"] and a["starting_cash"]
                for a in self.market.state()["agents"]
            )
        )


if __name__ == "__main__":
    unittest.main()
