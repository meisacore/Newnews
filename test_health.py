import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from economy import Market
from health import simulation_status


class HealthTests(unittest.TestCase):
    def test_brief_delay_is_not_reported_as_a_paused_simulation(self):
        self.assertEqual(simulation_status(1000, 1010)["status"], "live")
        self.assertEqual(simulation_status(1000, 1011)["status"], "delayed")
        self.assertTrue(simulation_status(1000, 1030)["running"])
        self.assertEqual(simulation_status(1000, 1031)["status"], "paused")
        self.assertFalse(simulation_status(None, 1000)["running"])

    def test_fresh_heartbeat_written_during_state_request_does_not_look_paused(self):
        with tempfile.TemporaryDirectory() as directory:
            market = Market(Path(directory) / "clock.sqlite3")
            with market.transaction() as db:
                db.execute("INSERT INTO meta VALUES('last_tick_at','1001')")
            with patch("economy.time.time", side_effect=[1000, 1001]):
                state = market.state()
            self.assertEqual(state["server_time"], 1001)
            self.assertEqual(state["simulation"]["status"], "live")
            self.assertTrue(state["simulation"]["running"])

    def test_tick_heartbeat_records_completion_time(self):
        with tempfile.TemporaryDirectory() as directory:
            market = Market(Path(directory) / "complete.sqlite3")
            with patch("economy.time.time", return_value=1000) as clock:

                def slow_launch(*args):
                    clock.return_value = 1015

                with patch.object(market, "_launch_due", side_effect=slow_launch):
                    market.tick(seed=0)
            with market.connection() as db:
                self.assertEqual(
                    db.execute(
                        "SELECT value FROM meta WHERE key='last_tick_at'"
                    ).fetchone()[0],
                    "1015",
                )

    def test_failed_tick_does_not_forge_a_successful_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            market = Market(Path(directory) / "failed.sqlite3")
            with market.transaction() as db:
                db.execute("INSERT INTO meta VALUES('last_tick_at','1000')")
            with patch.object(
                market, "_agent_decision", side_effect=RuntimeError("simulated failure")
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                    market.tick(seed=0)
            with market.connection() as db:
                self.assertEqual(
                    db.execute(
                        "SELECT value FROM meta WHERE key='last_tick_at'"
                    ).fetchone()[0],
                    "1000",
                )


if __name__ == "__main__":
    unittest.main()
