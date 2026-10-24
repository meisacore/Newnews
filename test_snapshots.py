import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from snapshots import PublicSnapshots


class PublicSnapshotTests(unittest.TestCase):
    def test_world_selection_expiry_and_capacity_are_independent(self):
        now = [0]
        cache = PublicSnapshots(ttl=2, capacity=2, clock=lambda: now[0])
        a, b = object(), object()
        self.assertEqual(cache.get(a, ("state", None), lambda: "a"), "a")
        self.assertEqual(cache.get(b, ("state", None), lambda: "b"), "b")
        self.assertEqual(cache.get(a, ("state", "frog"), lambda: "frog"), "frog")
        self.assertEqual(len(cache.values), 2)
        now[0] = 3
        self.assertEqual(cache.get(a, ("state", "frog"), lambda: "new"), "new")
        cache.invalidate(a)
        self.assertTrue(all(key[0] is not a for key in cache.values))

    def test_simultaneous_readers_share_one_database_call(self):
        cache = PublicSnapshots()
        calls = []

        def produce():
            calls.append(1)
            time.sleep(0.03)
            return {"public": True}

        world = object()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(lambda _: cache.get(world, ("state", None), produce), range(8))
            )
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(r == {"public": True} for r in results))

    def test_trade_invalidation_prevents_an_old_inflight_read_being_reused(self):
        cache = PublicSnapshots()
        world = object()
        started, finish = threading.Event(), threading.Event()

        def old():
            started.set()
            finish.wait(2)
            return "before trade"

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(cache.get, world, ("state", None), old)
            self.assertTrue(started.wait(1))
            cache.invalidate(world)
            self.assertEqual(
                cache.get(world, ("state", None), lambda: "after trade"), "after trade"
            )
            finish.set()
            self.assertEqual(pending.result(), "before trade")
        self.assertEqual(
            cache.get(world, ("state", None), lambda: "unexpected"), "after trade"
        )

    def test_failed_reads_are_not_cached(self):
        cache = PublicSnapshots()
        world = object()

        def fail():
            raise ValueError("failed")

        with self.assertRaises(ValueError):
            cache.get(world, ("state", None), fail)
        self.assertEqual(
            cache.get(world, ("state", None), lambda: "recovered"), "recovered"
        )


if __name__ == "__main__":
    unittest.main()
