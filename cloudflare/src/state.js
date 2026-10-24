import { UNIT, SUPPLY, POLICIES } from "./config.js";
import { rows, one, numericRow } from "./database.js";

const WINDOWS = { "5m": 300, "1h": 3600, "6h": 21600, "24h": 86400 };
export function publicTrade(row) {
  const value = numericRow(row);
  const policy = POLICIES[value.persona];
  value.account = value.agent_name ? value.account : "Player";
  value.agent_name ||= "Player";
  value.persona = policy?.[0] || null;
  return value;
}
export async function recentTrades(db, selected = null, large = false) {
  return (
    await rows(
      db,
      `SELECT t.*,p.name AS agent_name,p.persona FROM trades t
    LEFT JOIN agent_personas p ON p.account=t.account
    ${selected ? "WHERE t.coin=$1" : large ? "WHERE t.amount>=1000000000" : ""}
    ORDER BY t.id DESC LIMIT ${selected ? 50 : large ? 10 : 30}`,
      selected ? [selected] : [],
    )
  ).map(publicTrade);
}

export async function coinData(
  db,
  selected = null,
  now = Math.floor(Date.now() / 1000),
) {
  const raw = (
    await rows(
      db,
      `SELECT c.*,l.created_at,l.activity_goal,l.seed_cash,
    COALESCE(t.volume,0) AS total_volume,COALESCE(t.volume_24h,0) AS volume_24h,
    COALESCE(t.txns,0) AS txns,COALESCE(h.holders,0) AS holders,
    (SELECT qty FROM holdings WHERE account='treasury' AND coin=c.id) AS treasury_qty,
    (SELECT price FROM trades WHERE coin=c.id AND ts>=$1 ORDER BY ts,id LIMIT 1) AS first_price
    FROM coins c JOIN launches l ON l.coin=c.id
    LEFT JOIN (SELECT coin,SUM(amount) AS volume,SUM(CASE WHEN ts>=$1 THEN amount ELSE 0 END) AS volume_24h,COUNT(*) AS txns FROM trades ${selected ? "WHERE coin=$2" : ""} GROUP BY coin) t ON t.coin=c.id
    LEFT JOIN (SELECT coin,COUNT(*) AS holders FROM holdings WHERE account!='treasury' AND qty>0 ${selected ? "AND coin=$2" : ""} GROUP BY coin) h ON h.coin=c.id
    ${selected ? "WHERE c.id=$2" : ""} ORDER BY l.created_at DESC,c.id`,
      selected ? [now - 86400, selected] : [now - 86400],
    )
  ).map(numericRow);
  const windowStats = {},
    market_totals = {},
    hot = new Set();
  for (const [label, seconds] of Object.entries(WINDOWS)) {
    const stats = {};
    for (let row of await rows(
      db,
      `SELECT coin,
      SUM(CASE WHEN side='buy' THEN amount ELSE 0 END) AS buys,
      SUM(CASE WHEN side='sell' THEN amount ELSE 0 END) AS sells,
      SUM(CASE WHEN side='buy' THEN 1 ELSE 0 END) AS buy_count,
      SUM(CASE WHEN side='sell' THEN 1 ELSE 0 END) AS sell_count,
      COUNT(DISTINCT CASE WHEN side='buy' THEN account END) AS buyers,
      COUNT(DISTINCT account) AS traders,COUNT(*) AS txns,SUM(amount) AS volume
      FROM trades WHERE ts>=$1 AND ts<=$2 ${selected ? "AND coin=$3" : ""} GROUP BY coin`,
      selected ? [now - seconds, now, selected] : [now - seconds, now],
    )) {
      row = numericRow(row);
      row.volume = Number(row.volume);
      row.score =
        ((row.buys / UNIT) * Math.log2(2 + row.buyers) * row.buy_count) /
        Math.max(1, row.txns);
      stats[row.coin] = row;
    }
    windowStats[label] = stats;
    const values = Object.values(stats);
    market_totals[label] = {
      volume: values.reduce((n, v) => n + v.volume, 0) / UNIT,
      txns: values.reduce((n, v) => n + v.txns, 0),
    };
    values
      .sort((a, b) => b.score - a.score)
      .slice(0, 60)
      .forEach((v) => hot.add(v.coin));
  }
  const counts = { new: 0, stretch: 0, migrated: 0 },
    candidates = [];
  for (const r of raw) {
    const price = r.cash / r.tokens / UNIT,
      circulation = SUPPLY - r.treasury_qty;
    const progress = Math.min(100, (r.total_volume / r.activity_goal) * 100);
    const stage =
      progress >= 100 ? "migrated" : progress >= 70 ? "stretch" : "new";
    counts[stage]++;
    if (counts[stage] > 60 && !hot.has(r.id) && r.id !== selected) continue;
    const recent = windowStats["5m"][r.id] || {};
    candidates.push({
      id: r.id,
      name: r.name,
      symbol: r.symbol,
      price,
      circulating_supply: circulation,
      total_supply: SUPPLY,
      market_cap: price * circulation,
      fdv: price * SUPPLY,
      volume_24h: r.volume_24h / UNIT,
      change_24h: r.first_price ? (price / r.first_price - 1) * 100 : 0,
      pool_usd: r.cash / UNIT,
      created_at: r.created_at,
      progress,
      stage,
      txns: r.txns,
      holders: r.holders,
      in_feed: counts[stage] <= 60,
      buy_usd_5m: (recent.buys || 0) / UNIT,
      sell_usd_5m: (recent.sells || 0) / UNIT,
      buyers_5m: recent.buyers || 0,
      buys_5m: recent.buy_count || 0,
      sells_5m: recent.sell_count || 0,
      heat_score: recent.score || 0,
      windows: {},
    });
  }
  if (candidates.length)
    for (const [label, seconds] of Object.entries(WINDOWS)) {
      const baselines = new Map(
        (
          await rows(
            db,
            `SELECT c.id,COALESCE(
      (SELECT price FROM trades WHERE coin=c.id AND ts<=$1 ORDER BY ts DESC,id DESC LIMIT 1),
      (SELECT price FROM trades WHERE coin=c.id AND ts>$1 AND ts<=$2 ORDER BY ts,id LIMIT 1)) AS price
      FROM coins c WHERE c.id=ANY($3::text[])`,
            [now - seconds, now, candidates.map((c) => c.id)],
          )
        ).map((r) => [r.id, r.price]),
      );
      for (const c of candidates) {
        const s = windowStats[label][c.id] || {},
          baseline = baselines.get(c.id);
        c.windows[label] = {
          volume: (s.volume || 0) / UNIT,
          txns: s.txns || 0,
          traders: s.traders || 0,
          buy_usd: (s.buys || 0) / UNIT,
          sell_usd: (s.sells || 0) / UNIT,
          buyers: s.buyers || 0,
          buys: s.buy_count || 0,
          sells: s.sell_count || 0,
          heat: s.score || 0,
          change: baseline ? (c.price / baseline - 1) * 100 : null,
        };
      }
    }
  return {
    coins: candidates.filter((c) => c.in_feed || c.id === selected),
    screener: candidates.filter((c) => c.in_feed || hot.has(c.id)),
    trending: candidates
      .filter((c) => hot.has(c.id) && c.heat_score > 0)
      .sort((a, b) => b.heat_score - a.heat_score)
      .slice(0, 10),
    pulse_counts: counts,
    total_coins: Object.values(counts).reduce((a, b) => a + b, 0),
    market_totals,
  };
}

export async function buildState(db, now = Math.floor(Date.now() / 1000)) {
  const result = await coinData(db, null, now);
  const agents = (
    await rows(
      db,
      `SELECT a.id,a.cash,p.name,p.persona,g.amount AS starting_cash,
    COALESCE(t.trades,0) AS trades,COALESCE(t.biggest_buy,0) AS biggest_buy
    FROM accounts a JOIN agent_personas p ON p.account=a.id LEFT JOIN agent_grants g ON g.account=a.id
    LEFT JOIN (SELECT account,COUNT(*) AS trades,MAX(CASE WHEN side='buy' THEN amount ELSE 0 END) AS biggest_buy FROM trades GROUP BY account) t ON t.account=a.id WHERE a.kind='agent' ORDER BY a.id`,
    )
  ).map((row) => {
    const a = numericRow(row),
      p = POLICIES[a.persona];
    return {
      ...a,
      strategy: p[1],
      personality: p[0],
      disciplined: p[9],
      risk: p[2],
      patience: p[6],
    };
  });
  const meta = Object.fromEntries(
    (await rows(db, "SELECT key,value FROM meta")).map((r) => [r.key, r.value]),
  );
  return {
    ...result,
    api_version: 6,
    simulation: {
      running: true,
      status: "live",
      last_tick_at: now,
      age_seconds: 0,
    },
    trades: await recentTrades(db),
    large_trades: await recentTrades(db, null, true),
    coin_trades: [],
    trending_window_seconds: 300,
    agents,
    condition: meta.condition,
    simulated: true,
    next_launch_at: Number(meta.next_launch_at),
    server_time: now,
    launch_batch: 5,
  };
}

export async function account(db, identity) {
  const a = await one(db, "SELECT cash FROM accounts WHERE id=$1", [identity]);
  if (!a) return null;
  const holdings = Object.fromEntries(
    (
      await rows(db, "SELECT coin,qty FROM holdings WHERE account=$1", [
        identity,
      ])
    ).map((r) => [r.coin, Number(r.qty)]),
  );
  const trades = (
    await rows(
      db,
      "SELECT * FROM trades WHERE account=$1 ORDER BY id DESC LIMIT 50",
      [identity],
    )
  ).map(numericRow);
  const positions = (
    await rows(
      db,
      "SELECT c.id,c.name,c.symbol,h.qty,c.cash::double precision/c.tokens/1000000 AS price FROM holdings h JOIN coins c ON c.id=h.coin WHERE h.account=$1 AND h.qty>0 ORDER BY c.symbol",
      [identity],
    )
  ).map(numericRow);
  return {
    id: identity,
    cash: Number(a.cash) / UNIT,
    holdings,
    trades,
    positions,
  };
}

export async function candles(
  db,
  coin,
  interval,
  range,
  now = Math.floor(Date.now() / 1000),
) {
  if (!(await one(db, "SELECT 1 FROM coins WHERE id=$1", [coin]))) return null;
  const end = Math.floor(now / interval) * interval,
    start = end - range;
  const previous = await one(
    db,
    "SELECT price FROM trades WHERE coin=$1 AND ts<$2 ORDER BY ts DESC,id DESC LIMIT 1",
    [coin, start],
  );
  // Aggregate in PostgreSQL: never download a full day of individual executions.
  const buckets = new Map(
    (
      await rows(
        db,
        `SELECT floor(ts::numeric/$3)::bigint*$3 AS time,
    (array_agg(price ORDER BY ts,id))[1] AS open,max(price) AS high,min(price) AS low,
    (array_agg(price ORDER BY ts DESC,id DESC))[1] AS close,sum(amount)::double precision/1000000 AS volume
    FROM trades WHERE coin=$1 AND ts>=$2 AND ts<=$4 GROUP BY 1 ORDER BY 1`,
        [coin, start, interval, now],
      )
    ).map((r) => [Number(r.time), { ...r, time: Number(r.time) }]),
  );
  const result = [];
  let last = previous?.price ?? null;
  for (let time = start; time <= end; time += interval) {
    const b = buckets.get(time);
    if (b) {
      last = b.close;
      result.push(b);
    } else if (last !== null)
      result.push({
        time,
        open: last,
        high: last,
        low: last,
        close: last,
        volume: 0,
      });
  }
  return result;
}
