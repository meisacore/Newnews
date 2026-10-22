import test from "node:test";
import assert from "node:assert/strict";
import { validateMarketState } from "./marketState.js";

const valid = () => ({
  api_version: 3,
  coins: [{ id: "frog", stage: "new" }],
  next_launch_at: 1060,
  server_time: 1000,
  pulse_counts: { new: 1, stretch: 0, migrated: 0 },
  simulation: { running: true, last_tick_at: 1000 },
});
test("old backend response is rejected instead of displaying empty Pulse", () => {
  assert.throws(() => validateMarketState({...valid(),api_version:2}), /backend is out of date/);
  assert.throws(
    () => validateMarketState({ coins: [{ id: "frog", price: 0.2 }] }),
    /backend is out of date/,
  );
});
test("complete current feed and genuine paused feed are accepted", () => {
  const data = valid();
  assert.equal(validateMarketState(data), data);
  data.simulation = { running: false, last_tick_at: null };
  assert.equal(validateMarketState(data), data);
});
test("partial migrations and missing scheduling metadata are rejected", () => {
  for (const edit of [
    (d) => delete d.next_launch_at,
    (d) => delete d.simulation,
    (d) => delete d.coins[0].stage,
    (d) => (d.pulse_counts.new = null),
  ]) {
    const data = valid();
    edit(data);
    assert.throws(() => validateMarketState(data), /backend is out of date/);
  }
});
