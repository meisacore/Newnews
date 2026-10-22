import os
import time
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from worker import SimulationRunner, worker_lock


class WorkerLockTests(unittest.TestCase):
    def test_second_process_blocked_then_allowed_after_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "market.sqlite3"
            script = """
import sys
from filelock import Timeout
from worker import worker_lock
try:
    with worker_lock(sys.argv[1]):
        pass
except Timeout:
    sys.exit(23)
"""

            def attempt():
                return subprocess.run(
                    [sys.executable, "-c", script, str(path)],
                    cwd=Path(__file__).parent,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )

            with worker_lock(path):
                blocked = attempt()
                self.assertEqual(blocked.returncode, 23, blocked.stderr)
            allowed = attempt()
            self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_waiting_runner_takes_over_when_external_lock_is_released(self):
        from economy import Market

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.sqlite3"
            market = Market(path)
            runner = SimulationRunner(path, interval=0.02)
            try:
                with worker_lock(path):
                    runner.start()
                    time.sleep(0.1)
                    self.assertFalse(market.state()["simulation"]["running"])
                deadline = time.monotonic() + 5
                while not market.state()["simulation"]["running"]:
                    if time.monotonic() > deadline:
                        self.fail("Runner did not take ownership")
                    time.sleep(0.02)
            finally:
                runner.stop()
            with worker_lock(path):
                pass

    def test_default_database_location_does_not_depend_on_working_directory(self):
        project = Path(__file__).parent.resolve()
        env = {**os.environ, "PYTHONPATH": str(project), "NORX_DB": "data/norx.sqlite3"}
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from paths import database_path;print(database_path())",
                ],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
        self.assertEqual(Path(result.stdout.strip()), project / "data" / "norx.sqlite3")


if __name__ == "__main__":
    unittest.main()
