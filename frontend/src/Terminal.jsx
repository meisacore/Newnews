import React, { useState } from "react";
const usd = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: n < 1 ? 5 : 2,
  }).format(n || 0);
export function Discover({ state, onOpen, onBuy, busy }) {
  const [query, setQuery] = useState(""),
    [sort, setSort] = useState("volume_24h"),
    [stage, setStage] = useState("all");
  const rows = (state?.coins || [])
    .filter(
      (c) =>
        c.in_feed !== false &&
        (stage === "all" || c.stage === stage) &&
        (c.name + " " + c.symbol).toLowerCase().includes(query.toLowerCase()),
    )
    .sort((a, b) => (b[sort] || 0) - (a[sort] || 0));
  return (
    <section className="terminal-panel">
      <div className="table-toolbar">
        <div className="tabs">
          {[
            ["all", "All markets"],
            ["new", "New launches"],
            ["migrated", "Established"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={stage === id ? "active" : ""}
              onClick={() => setStage(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          aria-label="Search markets"
          placeholder="Search name or symbol…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          aria-label="Sort markets"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="volume_24h">Highest volume</option>
          <option value="change_24h">Top gainers</option>
          <option value="market_cap">Market cap</option>
          <option value="created_at">Newest</option>
        </select>
      </div>
      <div className="table-scroll">
        <table className="terminal-table">
          <thead>
            <tr>
              <th>Market / USD</th>
              <th>Price</th>
              <th>24h change</th>
              <th>Market cap</th>
              <th>24h volume</th>
              <th>Pool USD</th>
              <th>Holders</th>
              <th>Trade</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id}>
                <td>
                  <button className="market-name" onClick={() => onOpen(c.id)}>
                    <span className="market-avatar">
                      {c.symbol.slice(0, 2)}
                    </span>
                    <span>
                      <b>{c.name}</b>
                      <small>{c.symbol}</small>
                    </span>
                  </button>
                </td>
                <td>{usd(c.price)}</td>
                <td className={c.change_24h >= 0 ? "up" : "down"}>
                  {c.change_24h >= 0 ? "+" : ""}
                  {c.change_24h.toFixed(2)}%
                </td>
                <td>{usd(c.market_cap)}</td>
                <td>{usd(c.volume_24h)}</td>
                <td>{usd(c.pool_usd)}</td>
                <td>{c.holders}</td>
                <td>
                  <button
                    disabled={busy}
                    className="table-buy"
                    onClick={() => onBuy(c.id, 50)}
                  >
                    Buy $50
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <p className="empty-market">
          {state
            ? "No markets match your search."
            : "Connecting to the market…"}
        </p>
      )}
      <div className="table-caption">
        {rows.length} markets in the current feed · USD valuations · Select a
        market to open its chart
      </div>
    </section>
  );
}
export function Activity({ state, selected, me }) {
  const [tab, setTab] = useState("trades"),
    [side, setSide] = useState("all");
  const trades = (
    tab === "mine"
      ? me?.trades || []
      : state?.coin_trades || state?.trades || []
  ).filter((t) => t.coin === selected && (side === "all" || t.side === side));
  return (
    <section className="terminal-panel execution-feed">
      <div className="table-toolbar">
        <div className="tabs">
          <button
            className={tab === "trades" ? "active" : ""}
            onClick={() => setTab("trades")}
          >
            Market trades
          </button>
          <button
            className={tab === "mine" ? "active" : ""}
            onClick={() => setTab("mine")}
          >
            My trades
          </button>
        </div>
        <select
          aria-label="Filter trades"
          value={side}
          onChange={(e) => setSide(e.target.value)}
        >
          <option value="all">All sides</option>
          <option value="buy">Buys</option>
          <option value="sell">Sells</option>
        </select>
        <span className="muted">Recent executions</span>
      </div>
      <div className="table-scroll">
        <table className="terminal-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Side</th>
              <th>USD</th>
              <th>Tokens</th>
              <th>Trader</th>
              <th>Strategy</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id}>
                <td>{new Date(t.ts * 1000).toLocaleTimeString()}</td>
                <td className={t.side === "buy" ? "up" : "down"}>
                  {t.side.toUpperCase()}
                </td>
                <td>{usd(t.amount / 1e6)}</td>
                <td>{t.qty.toLocaleString()}</td>
                <td>
                  {t.agent_name ||
                    (t.account?.startsWith("agent-") ? t.account : "Player")}
                </td>
                <td className="muted">{t.persona || "Manual trade"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!trades.length && (
        <p className="empty-market">
          {tab === "mine" && !me
            ? "Sign in to see your executions."
            : "No matching executions in the recent feed."}
        </p>
      )}
    </section>
  );
}
