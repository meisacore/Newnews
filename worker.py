"""Run one simulation writer per database on Windows, macOS, or Linux."""

import logging
import os
import time
from pathlib import Path

from filelock import FileLock, Timeout

from economy import Market


def worker_lock(path):
    """Use an OS-backed lock; process exit also releases ownership."""
    database = Path(path).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(database) + ".worker.lock", timeout=0)


def run(path):
    with worker_lock(path):
        market = Market(path)
        logging.info("NORX simulation running; virtual USD only")
        while True:
            try:
                market.tick()
            except Exception:
                logging.exception("Tick rolled back; retrying next tick")
            time.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        run(os.getenv("NORX_DB", "data/norx.sqlite3"))
    except Timeout:
        raise SystemExit("A simulation worker already owns this database")
    except KeyboardInterrupt:
        pass
