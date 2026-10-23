import tempfile
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from economy import Market, UNIT
from scenarios import SCENARIOS


class ScenarioTests(unittest.TestCase):
    def test_saved_worlds_have_independent_accounts_and_quotes(self):
        with tempfile.TemporaryDirectory() as folder:
            markets = {
                key: Market(Path(folder) / (key + ".sqlite3"), scenario=key)
                for key in SCENARIOS
            }
            balanced = markets["balanced"]
            balanced.account("player")
            q = balanced.quote("player", "frog", "buy", 50 * UNIT)
            balanced.execute("player", q["id"], "independent-world")
            for key, market in markets.items():
                self.assertAlmostEqual(
                    market.account("player")["cash"],
                    9950 if key == "balanced" else 10000,
                    places=3,
                )
                if key != "balanced":
                    with self.assertRaises(ValueError):
                        market.execute("player", q["id"], "wrong-world-quote")
                reopened = Market(market.path)
                with reopened.connection() as db:
                    self.assertEqual(
                        db.execute(
                            "SELECT value FROM meta WHERE key='scenario'"
                        ).fetchone()[0],
                        key,
                    )

    def test_thin_pool_order_limit_and_profit_exit(self):
        from test_personalities import eager_rng

        with tempfile.TemporaryDirectory() as folder:
            market = Market(Path(folder) / "market.sqlite3")
            with market.transaction() as db:
                a = db.execute(
                    "SELECT a.*,p.* FROM accounts a JOIN agent_personas p ON a.id=p.account WHERE a.id='agent-whale-03'"
                ).fetchone()
                reserve = db.execute(
                    "SELECT cash FROM coins WHERE id='frog'"
                ).fetchone()[0]
                market._agent_decision(db, a, "frog", eager_rng())
                trade = db.execute(
                    "SELECT * FROM trades ORDER BY id DESC LIMIT 1"
                ).fetchone()
                self.assertLessEqual(trade["amount"], reserve * 0.15)
                # Another real participant buys, moving the actual reserve price.
                market_price = db.execute(
                    "SELECT * FROM coins WHERE id='frog'"
                ).fetchone()
                qty = market.quantity(market_price, 10000 * UNIT)
                market._trade(
                    db, "agent-whale-04", market_price, "buy", qty, "test demand"
                )
                self.assertTrue(market._agent_decision(db, a, "frog", eager_rng()))
                exit_trade = db.execute(
                    "SELECT * FROM trades ORDER BY id DESC LIMIT 1"
                ).fetchone()
                self.assertEqual(exit_trade["side"], "sell")
                self.assertIn("take profit", exit_trade["reason"])

    def test_owned_coin_outside_sample_is_reviewed(self):
        with tempfile.TemporaryDirectory() as folder:
            market = Market(Path(folder) / "market.sqlite3")
            market.account("owner")
            with market.transaction() as db:
                db.execute(
                    "UPDATE agent_personas SET next_tick=100000 WHERE account!='agent-whale-03'"
                )
                db.execute(
                    "UPDATE agent_personas SET next_tick=0 WHERE account='agent-whale-03'"
                )
                coin = db.execute("SELECT * FROM coins WHERE id='frog'").fetchone()
                market._trade(db, "agent-whale-03", coin, "buy", 1000, "position")
            # Even with the public new-market sample excluding FROG, the owner
            # must still review it. Observe decisions without altering the ledger.
            seen = []
            original = market._agent_decision

            def observe(db, agent, coin, rng):
                seen.append((agent["id"], coin))
                return original(db, agent, coin, rng)

            class ExcludeFrogFromMarketSample(random.Random):
                def sample(self, population, k, **kwargs):
                    if population and "tokens" in population[0].keys():
                        population = [row for row in population if row["id"] != "frog"]
                    return super().sample(population, min(k, len(population)), **kwargs)

            with (
                patch("economy.random.Random", ExcludeFrogFromMarketSample),
                patch.object(market, "_agent_decision", side_effect=observe),
            ):
                for seed in range(200):
                    market.tick(seed=seed, now=1000)
            self.assertTrue(
                ("agent-whale-03", "frog") in seen,
                "Owner must review a coin excluded from market samples",
            )


if __name__ == "__main__":
    unittest.main()
