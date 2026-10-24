"""Bounded, short-lived public snapshots with coalesced database reads."""

from collections import OrderedDict
from concurrent.futures import Future
import threading
import time


class PublicSnapshots:
    def __init__(self, ttl=2, capacity=64, clock=time.monotonic):
        self.ttl, self.capacity, self.clock = ttl, capacity, clock
        self.lock = threading.Lock()
        self.values = OrderedDict()
        self.flights = {}
        self.epochs = {}

    def invalidate(self, world):
        with self.lock:
            self.epochs[world] = self.epochs.get(world, 0) + 1
            for key in list(self.values):
                if key[0] is world:
                    del self.values[key]

    def get(self, world, arguments, produce):
        with self.lock:
            key = (world, self.epochs.get(world, 0), *arguments)
            cached = self.values.get(key)
            if cached and cached[0] > self.clock():
                self.values.move_to_end(key)
                return cached[1]
            future = self.flights.get(key)
            leader = future is None
            if leader:
                future = self.flights[key] = Future()
        if not leader:
            return future.result()
        try:
            result = produce()
            with self.lock:
                if key[1] == self.epochs.get(world, 0):
                    self.values[key] = (self.clock() + self.ttl, result)
                    self.values.move_to_end(key)
                    while len(self.values) > self.capacity:
                        self.values.popitem(last=False)
            future.set_result(result)
            return result
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self.lock:
                self.flights.pop(key, None)
