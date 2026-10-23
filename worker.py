"""One cross-platform simulation owner, standalone or managed by the API."""

import logging
import threading
from pathlib import Path

from filelock import FileLock, Timeout

from storage import PostgresTarget, postgres_worker_lock
from economy import Market
from paths import database_path


def worker_lock(path):
    if isinstance(path, PostgresTarget):
        return postgres_worker_lock(path)
    database = Path(path).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(database) + ".worker.lock", timeout=0)


class SimulationRunner:
    def __init__(self, path, interval=2):
        self.path = (
            path if isinstance(path, PostgresTarget) else str(Path(path).resolve())
        )
        self.interval = interval
        self.stopped = threading.Event()
        self.thread = None

    def run_forever(self):
        while not self.stopped.is_set():
            try:
                with worker_lock(self.path) as ownership:
                    market = Market(self.path)
                    logging.info("NORX simulation running; virtual USD only")
                    while not self.stopped.is_set():
                        if isinstance(self.path, PostgresTarget):
                            # Detect a lost ownership session before another tick.
                            ownership.execute("SELECT 1")
                        try:
                            market.tick()
                        except Exception:
                            logging.exception("Tick rolled back; retrying next tick")
                        self.stopped.wait(self.interval)
            except Timeout:
                # Another API instance or standalone worker is already advancing
                # this database. Retry so we can take over if that owner exits.
                self.stopped.wait(self.interval)
            except Exception:
                logging.exception("Simulation could not start; retrying")
                self.stopped.wait(self.interval)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(
            target=self.run_forever, name="norx-simulation", daemon=True
        )
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=20)


def run(path):
    SimulationRunner(path).run_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        run(database_path())
    except KeyboardInterrupt:
        pass
