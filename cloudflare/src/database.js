import pg from "pg";
import { ApiError, worldSchema } from "./config.js";

export function databaseUrl(env) {
  if (env.HYPERDRIVE?.connectionString) return env.HYPERDRIVE.connectionString;
  if (!env.DATABASE_URL) return null;
  let url;
  try {
    url = new URL(env.DATABASE_URL);
  } catch {
    throw new ApiError(503, "Invalid database configuration");
  }
  if (!["postgres:", "postgresql:"].includes(url.protocol) || !url.hostname)
    throw new ApiError(503, "Invalid database configuration");
  if (url.port === "6543")
    throw new ApiError(503, "Use the Supabase session pooler on port 5432");
  if (!["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
    const mode = url.searchParams.get("sslmode") || "require";
    if (!["require", "verify-ca", "verify-full"].includes(mode))
      throw new ApiError(503, "Remote PostgreSQL requires TLS");
    url.searchParams.set("sslmode", mode);
  }
  return url.toString();
}

// Each invocation owns and closes its connection. No session locks or global pools.
// Hyperdrive can be bound later as HYPERDRIVE; its cache must be disabled for ledger reads.
export async function withDatabase(
  env,
  world,
  operation,
  { write = false } = {},
) {
  const schema = worldSchema(env, world);
  const connectionString = databaseUrl(env);
  if (!connectionString)
    throw new ApiError(503, "Database connection has not been configured");
  const client = new pg.Client({
    connectionString,
    connectionTimeoutMillis: 5000,
    query_timeout: 18000,
  });
  client.on("error", () => {});
  try {
    await client.connect();
    await client.query("BEGIN");
    await client.query(`SET LOCAL search_path TO "${schema}"`);
    await client.query("SET LOCAL statement_timeout='15s'");
    await client.query("SET LOCAL lock_timeout='1500ms'");
    if (write)
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [
        "norx-write-" + schema,
      ]);
    return await operation(client, schema);
  } finally {
    // operation commits explicitly, otherwise roll back every incomplete transaction.
    try {
      await client.query("ROLLBACK");
    } catch {}
    try {
      await client.end();
    } catch {}
  }
}
export async function commit(db, result) {
  await db.query("COMMIT");
  return result;
}
export async function rows(db, sql, args = []) {
  return (await db.query(sql, args)).rows;
}
export async function one(db, sql, args = []) {
  return (await rows(db, sql, args))[0];
}
// pg deliberately returns BIGINT as strings. API contracts use safe integer JSON numbers.
export function numericRow(row) {
  if (!row) return row;
  const copy = { ...row };
  for (const key of [
    "cash",
    "tokens",
    "qty",
    "amount",
    "ts",
    "expires",
    "starting_cash",
    "trades",
    "biggest_buy",
    "created_at",
    "seed_cash",
    "activity_goal",
    "total_volume",
    "volume_24h",
    "txns",
    "holders",
    "treasury_qty",
    "buys",
    "sells",
    "buy_count",
    "sell_count",
    "buyers",
    "traders",
  ])
    if (copy[key] != null) copy[key] = Number(copy[key]);
  if (typeof copy.id === "string" && /^\d+$/.test(copy.id))
    copy.id = Number(copy.id);
  return copy;
}
