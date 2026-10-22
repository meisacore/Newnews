"""Run exactly one simulation writer per database; restart safely after deployment."""

import fcntl
import logging
import os
import time
from pathlib import Path
from economy import Market

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = os.getenv("NORX_DB", "data/norx.sqlite3")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path + ".worker.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A simulation worker already owns this database")
        market = Market(path)
        logging.info("NORX simulation running; virtual USD only")
        while True:
            try:
                market.tick()
            except Exception:
                logging.exception("Tick rolled back; retrying next tick")
            time.sleep(2)
