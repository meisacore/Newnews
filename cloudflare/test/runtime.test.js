import test from "node:test";
import assert from "node:assert/strict";
import { api, validateBody, errorResponse } from "../src/index.js";
import { worldSchema, ApiError } from "../src/config.js";
import { withDatabase, one, rows, databaseUrl } from "../src/database.js";
import { advance } from "../src/runtime.js";

const url = process.env.NORX_TEST_PG_SCHEMA_PREFIX
  ? process.env.NORX_TEST_POSTGRES_URL
  : null;
const env = {
  DATABASE_URL: url,
  PRIVY_APP_ID: "test-app",
  NORX_PG_SCHEMA_PREFIX: process.env.NORX_TEST_PG_SCHEMA_PREFIX,
};
const verify = async () => "did:privy:cloud-test";
const tasks = [];
const ctx = {
  waitUntil(p) {
    tasks.push(p);
  },
};
const request = (path, body, world = "balanced") =>
  new Request("https://norx.test/api/" + path, {
    headers: { "X-Norx-World": world },
    ...(body ? { method: "POST", body: JSON.stringify(body) } : {}),
  });
const call = async (path, body, world) => {
  const r = await api(request(path, body, world), env, ctx, {
    verify,
    edgeCache: null,
  });
  const result = await r.json();
  await Promise.all(tasks.splice(0));
  return result;
};

test("world and amount validation cannot inject SQL or fractional ledger units", () => {
  for (const w of [
    "__proto__",
    "constructor",
    "balanced;DROP TABLE accounts",
    "",
  ])
    assert.throws(() => worldSchema({}, w), ApiError);
  assert.equal(worldSchema({}, "bull"), "norx_bull");
  for (const budget of [
    0,
    -1,
    0.5,
    Number.MAX_SAFE_INTEGER + 1,
    "50000000",
    null,
    true,
  ])
    assert.throws(
      () => validateBody("/api/quote", { coin: "frog", side: "buy", budget }),
      ApiError,
    );
  assert.equal(
    validateBody("/api/quote", { coin: "frog", side: "buy", budget: 50000000 })
      .budget,
    50000000,
  );
  assert.equal(errorResponse({ code: "55P03" }).status, 503);
});

test("database URLs enforce TLS without accepting transaction poolers", () => {
  assert.equal(
    new URL(
      databaseUrl({
        DATABASE_URL: "postgresql://u:p@example.com:5432/postgres",
      }),
    ).searchParams.get("sslmode"),
    "require",
  );
  assert.throws(
    () =>
      databaseUrl({
        DATABASE_URL:
          "postgresql://u:p@example.com:5432/postgres?sslmode=disable",
      }),
    ApiError,
  );
  assert.throws(
    () =>
      databaseUrl({
        DATABASE_URL: "postgresql://u:p@example.com:6543/postgres",
      }),
    ApiError,
  );
  assert.throws(
    () => databaseUrl({ DATABASE_URL: "https://example.com" }),
    ApiError,
  );
  assert.equal(
    databaseUrl({
      HYPERDRIVE: { connectionString: "postgresql://hyperdrive" },
    }),
    "postgresql://hyperdrive",
  );
});

test(
  "real PostgreSQL cutover: batches, conserved ledger, private trades and isolated worlds",
  { skip: !url },
  async () => {
    const first = await advance(env, "balanced", { visit: true });
    assert.equal(first.api_version, 6);
    assert.equal(first.agents.length, 2000);
    assert.equal(first.coins[0].total_supply, 1e9);
    const me = await call("me");
    assert.equal(me.cash, 10000);
    const totals = () =>
      withDatabase(env, "balanced", (db) =>
        one(
          db,
          "SELECT (SELECT sum(cash) FROM accounts)+(SELECT sum(cash) FROM coins) AS cash",
        ),
      );
    const before = await totals();
    const quote = await call("quote", {
      coin: "frog",
      side: "buy",
      budget: 50000000,
    });
    const results = await Promise.all([
      call("trade", { quote_id: quote.id, request_id: "cloud-trade-0001" }),
      call("trade", { quote_id: quote.id, request_id: "cloud-trade-0001" }),
    ]);
    assert.deepEqual(results[0], results[1]);
    assert.ok(results[0].usd <= 50);
    assert.equal((await totals()).cash, before.cash);
    const account = await call("me");
    assert.equal(account.holdings.frog, quote.qty);
    assert.equal(
      account.trades.filter((t) => t.reason === "Player trade").length,
      1,
    );
    assert.ok(account.cash < 10000 && account.cash >= 9950);
    assert.equal((await call("me", null, "bull")).cash, 10000);
    const state = await call("state?selected=frog");
    assert.equal(
      state.coin_trades.filter((t) => t.account === "did:privy:cloud-test")
        .length,
      0,
    );
    assert.ok(state.coin_trades.some((t) => t.account === "Player"));
    const chart = await call("candles/frog?interval=60&range_seconds=86400");
    assert.ok(chart.length > 0);
    assert.ok(chart.length <= 1441);
    const sale = await call("quote", {
      coin: "frog",
      side: "sell",
      qty: quote.qty,
    });
    await call("trade", { quote_id: sale.id, request_id: "cloud-sell-0001" });
    assert.equal((await call("me")).holdings.frog, 0);
    assert.equal((await totals()).cash, before.cash);
    await withDatabase(env, "balanced", async (db) => {
      const bad = await rows(
        db,
        "SELECT c.id FROM coins c LEFT JOIN holdings h ON h.coin=c.id GROUP BY c.id HAVING c.tokens+coalesce(sum(h.qty),0)<>1000000000",
      );
      assert.equal(bad.length, 0);
      const negatives = await one(
        db,
        "SELECT count(*) AS count FROM accounts WHERE cash<0",
      );
      assert.equal(Number(negatives.count), 0);
    });
    const count = await withDatabase(env, "balanced", (db) =>
      one(db, "SELECT count(*) AS count FROM coins"),
    );
    const future = Math.floor(Date.now() / 1000) + 65;
    const batch = await advance(env, "balanced", { visit: true, now: future });
    assert.equal(batch.total_coins, Number(count.count) + 5);
    const duplicate = await advance(env, "balanced", {
      visit: true,
      now: future,
    });
    assert.equal(duplicate.total_coins, batch.total_coins);
    // A dormant world doesn't catch up hundreds of missed launches on wake.
    const wake = await advance(env, "balanced", {
      visit: true,
      now: future + 1000,
    });
    assert.equal(wake.total_coins, batch.total_coins);
    const idle = await advance(env, "balanced", { now: future + 2000 });
    assert.equal(idle, null);
  },
);
