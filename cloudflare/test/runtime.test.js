import test from "node:test";
import assert from "node:assert/strict";
import { api, validateBody, errorResponse } from "../src/index.js";
import { worldSchema, ApiError } from "../src/config.js";
import { withDatabase, one, rows, databaseUrl } from "../src/database.js";
import { advance, readSnapshot } from "../src/runtime.js";
import { buildState } from "../src/state.js";
import { POLICIES } from "../src/config.js";

const url = process.env.NORX_TEST_PG_SCHEMA_PREFIX
  ? process.env.NORX_TEST_POSTGRES_URL
  : null;
const env = {
  DATABASE_URL: url,
  PRIVY_APP_ID: "test-app",
  NORX_PG_SCHEMA_PREFIX: process.env.NORX_TEST_PG_SCHEMA_PREFIX,
};
async function advanceImage(env, world, options = {}) {
  if (!(await advance(env, world, options))) return null;
  return JSON.parse(
    (await readSnapshot(env, world, { agents: true, now: options.now })).body,
  );
}
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
    const first = await advanceImage(env, "balanced", { visit: true });
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
    assert.equal(state.agent_count, 2000);
    assert.equal(state.agents.length, 0);
    assert.equal((await call("state?agents=1")).agents.length, 2000);
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
    const batch = await advanceImage(env, "balanced", {
      visit: true,
      now: future,
    });
    assert.equal(batch.total_coins, Number(count.count) + 5);
    const duplicate = await advanceImage(env, "balanced", {
      visit: true,
      now: future,
    });
    assert.equal(duplicate.total_coins, batch.total_coins);
    // A dormant world doesn't catch up hundreds of missed launches on wake.
    const wake = await advanceImage(env, "balanced", {
      visit: true,
      now: future + 1000,
    });
    assert.equal(wake.total_coins, batch.total_coins);
    const idle = await advanceImage(env, "balanced", { now: future + 2000 });
    assert.equal(idle, null);
  },
);

test(
  "first sign-in and concurrent grants do not wait on the world writer lock",
  { skip: !url },
  async () => {
    let acquired, release;
    const ready = new Promise((resolve) => {
      acquired = resolve;
    });
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    const holder = withDatabase(
      env,
      "balanced",
      async (db) => {
        acquired();
        await gate;
      },
      { write: true },
    );
    await ready;
    const user = "did:privy:registration-during-batch";
    try {
      const accounts = await Promise.all(
        Array.from({ length: 6 }, async () => {
          const response = await api(request("me"), env, ctx, {
            verify: async () => user,
            edgeCache: null,
          });
          assert.equal(response.status, 200);
          return response.json();
        }),
      );
      for (const a of accounts) {
        assert.equal(a.cash, 10000);
        assert.deepEqual(a.holdings, {});
      }
      const grant = await withDatabase(env, "balanced", (db) =>
        one(
          db,
          "SELECT count(*) AS accounts,sum(cash) AS cash FROM accounts WHERE id=$1",
          [user],
        ),
      );
      assert.equal(Number(grant.accounts), 1);
      assert.equal(Number(grant.cash), 10000000000);
    } finally {
      release();
      await holder;
    }
  },
);

test(
  "PostgreSQL snapshots preserve all public metrics at production-sized history",
  { skip: !url },
  async () => {
    await withDatabase(env, "balanced", async (db) => {
      // Disposable read-model fixture: large history reproduces the row volume
      // that exceeded CPU when it was downloaded and rendered inside a Worker.
      await db.query(`INSERT INTO coins(id,name,symbol,cash,tokens,reference)
      SELECT 'cpu-'||n,'CPU fixture '||n,'CPU'||n,10000000000,100000000,.0001 FROM generate_series(1,2200) n`);
      await db.query(
        `INSERT INTO holdings(account,coin,qty) SELECT 'treasury',id,900000000 FROM coins WHERE id LIKE 'cpu-%'`,
      );
      await db.query(
        `INSERT INTO launches(coin,created_at,seed_cash,activity_goal) SELECT id,$1-1000,10000000000,10000000000 FROM coins WHERE id LIKE 'cpu-%'`,
        [Math.floor(Date.now() / 1000)],
      );
      await db.query(
        `INSERT INTO trades(ts,account,coin,side,qty,amount,price,reason)
      SELECT $1-(n%86400),'fixture-human-'||(n%1200),'cpu-'||(1+(n%2200)),
        CASE WHEN n%3=0 THEN 'sell' ELSE 'buy' END,100,10000,.0001,'Read model fixture'
      FROM generate_series(1,260000) n`,
        [Math.floor(Date.now() / 1000)],
      );
      const now = Math.floor(Date.now() / 1000);
      const legacy = await buildState(db, now);
      const modern = (
        await one(db, "SELECT norx_build_state($1,$2::jsonb) AS value", [
          now,
          JSON.stringify(POLICIES),
        ])
      ).value;
      function same(actual, expected, path = "snapshot") {
        if (typeof expected === "number") {
          assert.ok(
            Math.abs(actual - expected) <=
              Math.max(1e-9, Math.abs(expected) * 1e-10),
            path + ": " + actual + " != " + expected,
          );
          return;
        }
        if (Array.isArray(expected)) {
          if (
            path.endsWith("trending") ||
            path.endsWith("screener") ||
            path.endsWith("coins")
          ) {
            expected = [...expected].sort((a, b) => a.id.localeCompare(b.id));
            actual = [...actual].sort((a, b) => a.id.localeCompare(b.id));
          }
          assert.equal(actual.length, expected.length, path + " length");
          expected.forEach((v, i) => same(actual[i], v, path + "[" + i + "]"));
          return;
        }
        if (expected && typeof expected === "object") {
          assert.deepEqual(
            Object.keys(actual).sort(),
            Object.keys(expected).sort(),
            path + " fields",
          );
          for (const k of Object.keys(expected))
            same(actual[k], expected[k], path + "." + k);
          return;
        }
        assert.equal(actual, expected, path);
      }
      // Exact selection among equally ranked heat scores can differ by stable tie
      // ordering; compare every coin that both implementations include.
      const expectedIds = new Set(legacy.coins.map((c) => c.id));
      modern.coins = modern.coins.filter((c) => expectedIds.has(c.id));
      const actualIds = new Set(modern.coins.map((c) => c.id));
      legacy.coins = legacy.coins.filter((c) => actualIds.has(c.id));
      const screenerIds = new Set(legacy.screener.map((c) => c.id));
      modern.screener = modern.screener.filter((c) => screenerIds.has(c.id));
      const seen = new Set(modern.screener.map((c) => c.id));
      legacy.screener = legacy.screener.filter((c) => seen.has(c.id));
      const trendIds = new Set(legacy.trending.map((c) => c.id));
      modern.trending = modern.trending.filter((c) => trendIds.has(c.id));
      const trendSeen = new Set(modern.trending.map((c) => c.id));
      legacy.trending = legacy.trending.filter((c) => trendSeen.has(c.id));
      same(modern, legacy);
      // Large fixtures stay only in this rolled-back test transaction.
    });
  },
);
