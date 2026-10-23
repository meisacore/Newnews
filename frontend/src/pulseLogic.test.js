import test from "node:test";
import assert from "node:assert/strict";
import { filterPulseRows, sortPulseRows, BUY_PRESETS } from "./pulseLogic.js";
const rows = [
  {
    id: "a",
    name: "Moon Frog",
    symbol: "FROG",
    market_cap: 10000,
    volume_24h: 2000,
    holders: 5,
    created_at: 900,
  },
  {
    id: "b",
    name: "Orbit Cloud",
    symbol: "ORBT",
    market_cap: 30000,
    volume_24h: 100,
    holders: 1,
    created_at: 950,
  },
];
test("Pulse filters use known USD, age, and holder values", () => {
  assert.deepEqual(
    filterPulseRows(rows, "", { minCap: "20000" }, 1000).map((c) => c.id),
    ["b"],
  );
  assert.deepEqual(
    filterPulseRows(rows, "", { maxAge: "1", minHolders: "1" }, 1000).map(
      (c) => c.id,
    ),
    ["b"],
  );
  assert.deepEqual(
    filterPulseRows(rows, "", { minVolume: "1000" }, 1000).map((c) => c.id),
    ["a"],
  );
  assert.equal(filterPulseRows(rows, "", { minCap: "30001" }, 1000).length, 0);
});
test("unknown figures are excluded by an active filter even when its bound is zero", () => {
  assert.equal(
    filterPulseRows(
      [{ ...rows[0], market_cap: undefined }],
      "",
      { minCap: "0" },
      1000,
    ).length,
    0,
  );
  assert.equal(
    filterPulseRows([{ ...rows[0], market_cap: undefined }], "", {}, 1000)
      .length,
    1,
  );
});
test("comma-separated search is case-insensitive and sorting does not mutate snapshots", () => {
  assert.equal(filterPulseRows(rows, "frog, ORBT", {}, 1000).length, 2);
  assert.deepEqual(
    sortPulseRows(rows, "cap").map((c) => c.id),
    ["b", "a"],
  );
  assert.deepEqual(
    sortPulseRows(rows, "volume").map((c) => c.id),
    ["a", "b"],
  );
  assert.deepEqual(
    rows.map((c) => c.id),
    ["a", "b"],
  );
  assert.deepEqual(BUY_PRESETS, [25, 50, 250]);
});
