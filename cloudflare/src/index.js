import { databaseFailure, logFailure } from "./diagnostics.js";
import { ApiError, SCENARIOS, worldSchema } from "./config.js";
import { withDatabase, one, commit } from "./database.js";
import { account, candles, coinData, recentTrades } from "./state.js";
import { advance, readSnapshot, scheduled } from "./runtime.js";
import { identity } from "./auth.js";

const json = (data, status = 200, headers = {}) =>
  Response.json(data, {
    status,
    headers: { "Cache-Control": "no-store", ...headers },
  });
const nowSeconds = () => Math.floor(Date.now() / 1000);
function text(value, max = 64) {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}
function integer(value) {
  return Number.isSafeInteger(value) && value > 0;
}
export function validateBody(path, b) {
  if (!b || typeof b !== "object" || Array.isArray(b))
    throw new ApiError(400, "Invalid request");
  if (path === "/api/quote") {
    if (
      !text(b.coin, 32) ||
      !["buy", "sell"].includes(b.side) ||
      (b.side === "buy" ? !integer(b.budget) : !integer(b.qty))
    )
      throw new ApiError(
        400,
        "Choose a valid token, side and positive whole amount",
      );
  } else if (
    !text(b.quote_id) ||
    !text(b.request_id) ||
    b.request_id.length < 8
  )
    throw new ApiError(400, "Invalid quote or request ID");
  return b;
}
function background(ctx, operation) {
  ctx.waitUntil(
    operation.catch((error) => logFailure("NORX market refresh failed", error)),
  );
}
// Only public snapshots/charts use the edge cache, and only after authentication
// headers have been removed from its key. Private endpoints never enter it.
function cacheKey(request, world) {
  const original = new URL(request.url);
  const url = new URL(original.pathname, original.origin);
  if (original.pathname === "/api/state") {
    const selected = original.searchParams.get("selected");
    if (selected) url.searchParams.set("selected", selected);
  } else {
    url.searchParams.set(
      "interval",
      original.searchParams.get("interval") || "60",
    );
    url.searchParams.set(
      "range_seconds",
      original.searchParams.get("range_seconds") || "7200",
    );
  }
  url.searchParams.set("__world", world);
  return new Request(url, { method: "GET" });
}
export async function api(
  request,
  env,
  ctx,
  { verify = identity, edgeCache = globalThis.caches?.default } = {},
) {
  const url = new URL(request.url),
    path = url.pathname;
  const world = request.headers.get("X-Norx-World") || "balanced";
  worldSchema(env, world);
  if (path === "/api/config" && request.method === "GET")
    return json({
      dev_auth: false,
      privy_configured: Boolean(env.PRIVY_APP_ID),
      economies: SCENARIOS,
    });
  const publicRoute =
    request.method === "GET" &&
    (path === "/api/state" || /^\/api\/candles\/[^/]+$/.test(path));
  const key = publicRoute ? cacheKey(request, world) : null;
  if (key && edgeCache) {
    const hit = await edgeCache.match(key);
    if (hit)
      return new Response(hit.body, {
        status: hit.status,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
      });
  }
  let value;
  if (path === "/api/state" && request.method === "GET") {
    const selected = url.searchParams.get("selected");
    if (selected && !text(selected, 32))
      throw new ApiError(400, "Invalid token");
    let control = await readSnapshot(env, world);
    if (!control?.snapshot) {
      // A competing refresh can briefly own the lock: retry on the next poll.
      const snapshot = await advance(env, world, { visit: true });
      if (!snapshot)
        throw new ApiError(503, "Market is starting. Please retry shortly.");
      control = {
        snapshot,
        snapshot_at: nowSeconds(),
        next_batch_at: nowSeconds() + 10,
        active_until: nowSeconds() + 120,
      };
    } else if (
      Number(control.next_batch_at) <= nowSeconds() ||
      Number(control.active_until) < nowSeconds() + 60
    ) {
      background(ctx, advance(env, world, { visit: true }));
    }
    value = structuredClone(control.snapshot);
    const age = Math.max(0, nowSeconds() - Number(control.snapshot_at));
    // Minute cron and request-driven batches have a wider heartbeat than Python.
    value.simulation = {
      running: age <= 90,
      status: age <= 20 ? "live" : age <= 90 ? "delayed" : "paused",
      last_tick_at: Number(control.snapshot_at),
      age_seconds: age,
    };
    value.server_time = nowSeconds();
    if (selected)
      await withDatabase(env, world, async (db) => {
        if (!value.coins.some((c) => c.id === selected)) {
          const extra = await coinData(db, selected);
          value.coins.push(
            ...extra.coins.map((c) => ({ ...c, in_feed: false })),
          );
        }
        value.coin_trades = await recentTrades(db, selected);
      });
  } else if (/^\/api\/candles\/[^/]+$/.test(path) && request.method === "GET") {
    const interval = Number(url.searchParams.get("interval") || 60),
      range = Number(url.searchParams.get("range_seconds") || 7200);
    if (
      ![60, 300, 900, 3600].includes(interval) ||
      ![7200, 86400].includes(range)
    )
      throw new ApiError(400, "Unsupported chart interval or range");
    let coin;
    try {
      coin = decodeURIComponent(path.slice("/api/candles/".length));
    } catch {
      throw new ApiError(400, "Invalid token");
    }
    if (!text(coin, 32)) throw new ApiError(400, "Invalid token");
    value = await withDatabase(env, world, (db) =>
      candles(db, coin, interval, range),
    );
    if (value === null) throw new ApiError(400, "Unknown coin");
  } else if (path === "/api/me" && request.method === "GET") {
    const user = await verify(request, env);
    value = await withDatabase(env, world, async (db) => {
      // Snapshot reads never wait for a simulation writer's advisory lock.
      await db.query(
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
      );
      return account(db, user);
    });
    if (!value)
      value = await withDatabase(
        env,
        world,
        async (db) => {
          await db.query(
            "INSERT INTO accounts(id,cash,kind) VALUES($1,10000000000,'human') ON CONFLICT DO NOTHING",
            [user],
          );
          return commit(db, await account(db, user));
        },
        { write: true },
      );
  } else if (
    ["/api/quote", "/api/trade"].includes(path) &&
    request.method === "POST"
  ) {
    const user = await verify(request, env);
    // Cap streamed bodies too, rather than trusting a client Content-Length.
    const reader = request.body?.getReader();
    if (!reader) throw new ApiError(400, "Invalid request");
    let size = 0,
      chunks = [];
    while (true) {
      const { value: chunk, done } = await reader.read();
      if (done) break;
      size += chunk.byteLength;
      if (size > 4096) {
        await reader.cancel();
        throw new ApiError(413, "Request too large");
      }
      chunks.push(chunk);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const c of chunks) {
      bytes.set(c, offset);
      offset += c.length;
    }
    let body;
    try {
      body = validateBody(path, JSON.parse(new TextDecoder().decode(bytes)));
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(400, "Invalid JSON request");
    }
    value = await withDatabase(
      env,
      world,
      async (db) => {
        const r =
          path === "/api/quote"
            ? await one(db, "SELECT norx_quote($1,$2,$3,$4,$5,$6) AS result", [
                user,
                body.coin,
                body.side,
                body.budget ?? null,
                body.qty ?? null,
                crypto.randomUUID(),
              ])
            : await one(db, "SELECT norx_execute($1,$2,$3) AS result", [
                user,
                body.quote_id,
                body.request_id,
              ]);
        return commit(db, r.result);
      },
      { write: true },
    );
    if (path === "/api/trade") {
      // Private balance/receipt is immediate. Public prices refresh within one poll.
      background(ctx, advance(env, world, { visit: true }));
      if (edgeCache)
        for (const suffix of [
          "",
          `?selected=${encodeURIComponent(value.coin)}`,
        ])
          background(
            ctx,
            edgeCache.delete(
              cacheKey(new Request(url.origin + "/api/state" + suffix), world),
            ),
          );
    }
  } else throw new ApiError(404, "API route not found");
  if (key && edgeCache)
    background(
      ctx,
      edgeCache.put(
        key,
        Response.json(value, {
          headers: { "Cache-Control": "public,max-age=5" },
        }),
      ),
    );
  return json(value);
}
export function errorResponse(error) {
  if (error instanceof ApiError)
    return json({ detail: error.message }, error.status);
  if (error.code === "P0001") return json({ detail: error.message }, 400);
  if (
    ["55P03", "57014", "53300", "57P01", "ECONNRESET", "ETIMEDOUT"].includes(
      error.code,
    )
  )
    return json({ detail: "The market is busy. Please retry shortly." }, 503, {
      "Retry-After": "2",
    });
  logFailure("NORX API failed", error);
  return json({ detail: databaseFailure(error).hint }, 503, {
    "Retry-After": "2",
  });
}
export default {
  async fetch(request, env, ctx) {
    const path = new URL(request.url).pathname;
    if (!path.startsWith("/api/")) {
      if (path === "/")
        return env.ASSETS.fetch(
          new Request(new URL("/index.html", request.url), request),
        );
      return env.ASSETS.fetch(request);
    }
    try {
      return await api(request, env, ctx);
    } catch (error) {
      return errorResponse(error);
    }
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(scheduled(env));
  },
};
