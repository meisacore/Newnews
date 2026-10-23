import { test } from "node:test";
import assert from "node:assert/strict";
import { toUsd, fromUsd, formatMoney, SIM_ETH_USD } from "./money.js";
test("fictional ETH budgets convert to USD without changing the underlying ledger unit", () => {
  assert.equal(SIM_ETH_USD, 3000);
  assert.equal(toUsd(0.1, "ETH"), 300);
  assert.equal(Math.round(toUsd(0.01, "ETH") * 1e6), 30000000);
  assert.equal(toUsd(50, "USD"), 50);
  assert.equal(fromUsd(300, "ETH"), 0.1);
});
test("display conversion preserves sign and small nonzero prices", () => {
  assert.equal(formatMoney(3000, "ETH"), "1 ETH");
  assert.equal(formatMoney(-300, "ETH"), "-0.1 ETH");
  assert.equal(formatMoney(50, "USD"), "$50.00");
  assert.notEqual(formatMoney(0.00000001, "ETH"), "0 ETH");
});
