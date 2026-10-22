import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from worker import worker_lock


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


if __name__ == "__main__":
    unittest.main()
