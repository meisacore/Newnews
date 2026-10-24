import test from "node:test";
import assert from "node:assert/strict";
import { PublicCache, isPublicMarketPath } from "./publicCache.js";

test("private requests cannot enter the public cache", async () => {
  const cache = new PublicCache();
  for (const path of [
    "me",
    "quote",
    "trade",
    "../me",
    "https://elsewhere/api/state",
  ]) {
    assert.equal(isPublicMarketPath(path), false);
    await assert.rejects(
      cache.get("balanced", path, () => ({ private: true })),
    );
  }
});
test("coalesces public reads while preserving worlds, expiry and size bounds", async () => {
  let now = 0,
    calls = 0;
  const cache = new PublicCache({ clock: () => now, ttl: 8, capacity: 2 });
  const produce = async () => {
    calls++;
    return "shared";
  };
  assert.deepEqual(
    await Promise.all([
      cache.get("balanced", "state", produce),
      cache.get("balanced", "state", produce),
    ]),
    ["shared", "shared"],
  );
  assert.equal(calls, 1);
  await cache.get("bull", "state", produce);
  assert.equal(calls, 2);
  now = 9;
  await cache.get("balanced", "state", produce);
  assert.equal(calls, 3);
  await cache.get("balanced", "candles/frog", produce);
  assert.equal(cache.values.size, 2);
});
test("invalidation does not reuse a pre-trade in-flight request", async () => {
  const cache = new PublicCache();
  let finish;
  const pending = cache.get(
    "balanced",
    "state",
    () => new Promise((resolve) => (finish = resolve)),
  );
  await Promise.resolve();
  cache.invalidate("balanced");
  assert.equal(await cache.get("balanced", "state", () => "after"), "after");
  finish("before");
  assert.equal(await pending, "before");
  assert.equal(await cache.get("balanced", "state", () => "wrong"), "after");
});
