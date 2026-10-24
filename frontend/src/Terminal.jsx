import React, { useState } from "react";
import { Flame, TrendingUp, Sprout, BarChart3, Waves } from "lucide-react";
import { useCurrency } from "./Currency";
const WINDOWS = ["5m", "1h", "6h", "24h"];
function age(ts, now) {
  const seconds = Math.max(0, now - ts);
  return seconds < 60
    ? Math.floor(seconds) + "s"
    : seconds < 3600
      ? Math.floor(seconds / 60) + "m"
      : seconds < 86400
        ? Math.floor(seconds / 3600) + "h"
        : Math.floor(seconds / 86400) + "d";
}
function Percent({ value }) {
  return (
    <span className={value == null ? "muted" : value >= 0 ? "up" : "down"}>
      {value == null ? "—" : (value >= 0 ? "+" : "") + value.toFixed(2) + "%"}
    </span>
  );
}
export function Discover({
  state,
  onOpen,
  onBuy,
  busy,
  picker = false,
  onWhales,
}) {
  const money = useCurrency();
  const [query, setQuery] = useState(""),
    [mode, setMode] = useState(picker ? "all" : "trending"),
    [window, setWindow] = useState("5m"),
    [sort, setSort] = useState(picker ? "volume" : "heat"),
    [desc, setDesc] = useState(true);
  const data = state?.screener || state?.coins || [];
  const metric = (c) => c.windows?.[window] || {};
  const numeric = (c, key) =>
    key === "market_cap" ||
    key === "price" ||
    key === "created_at" ||
    key === "holders"
      ? c[key]
      : key.startsWith("change_")
        ? c.windows?.[key.slice(7)]?.change
        : metric(c)[key];
  const rows = data
    .filter(
      (c) =>
        (c.name + " " + c.symbol + " " + c.id)
          .toLowerCase()
          .includes(query.toLowerCase()) &&
        (mode !== "new" || c.stage === "new") &&
        (mode !== "established" || c.stage === "migrated") &&
        (mode !== "trending" || (metric(c).heat || 0) > 0),
    )
    .sort(
      (a, b) =>
        (desc ? -1 : 1) *
        ((numeric(a, sort) ?? -Infinity) - (numeric(b, sort) ?? -Infinity)),
    );
  function choose(id) {
    setMode(id);
    setDesc(true);
    setSort(
      id === "trending"
        ? "heat"
        : id === "gainers"
          ? "change"
          : id === "top"
            ? "market_cap"
            : id === "new"
              ? "created_at"
              : "volume",
    );
  }
  function sortBy(key) {
    if (sort === key) setDesc(!desc);
    else {
      setSort(key);
      setDesc(true);
    }
  }
  const total = state?.market_totals?.[window];
  const headers = [
    ["Token", null],
    ["Mcap", "market_cap"],
    ["Price", "price"],
    ["Age", "created_at"],
    ["Txns", "txns"],
    ["Volume", "volume"],
    ["Traders", "traders"],
    ["5m", "change_5m"],
    ["1h", "change_1h"],
    ["6h", "change_6h"],
    ["24h", "change_24h"],
    ["Buy / sell", null],
    ["Trade", null],
  ];
  return (
    <section className="screener" aria-label="Market screener">
      <div className="screener-stats">
        <div>
          <span>{window.toUpperCase()} VOLUME</span>
          <b>{total ? money.compact(total.volume) : "—"}</b>
        </div>
        <div>
          <span>{window.toUpperCase()} TRANSACTIONS</span>
          <b>{total ? total.txns.toLocaleString() : "—"}</b>
        </div>
        <div>
          <span>MARKETS</span>
          <b>{state?.total_coins?.toLocaleString() ?? "—"}</b>
        </div>
      </div>
      <div className="screener-controls">
        <div className="screener-modes">
          {[
            ["trending", "Trending", Flame],
            ["top", "Top", BarChart3],
            ["gainers", "Gainers", TrendingUp],
            ["new", "New pairs", Sprout],
            ["all", "All markets", null],
            ["established", "Established", null],
          ].map(([id, label, Icon]) => (
            <button
              key={id}
              className={mode === id ? "active" : ""}
              onClick={() => choose(id)}
            >
              {Icon && <Icon size={13} />}
              <span>{label}</span>
            </button>
          ))}
        </div>
        <div
          className="screener-windows"
          role="group"
          aria-label="Activity window"
        >
          {WINDOWS.map((w) => (
            <button
              key={w}
              aria-pressed={w === window}
              onClick={() => setWindow(w)}
            >
              {w.toUpperCase()}
            </button>
          ))}
        </div>
        <input
          aria-label="Search markets"
          placeholder="Search token or symbol…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="screener-whales" onClick={onWhales}>
          <Waves size={14} />
          Whale watch
        </button>
      </div>
      <div className="screener-table-wrap">
        <table className="screener-table">
          <thead>
            <tr>
              {headers.map(([label, key]) => (
                <th key={label}>
                  {key ? (
                    <button
                      aria-label={"Sort by " + label}
                      onClick={() => sortBy(key)}
                    >
                      {label}
                      {sort === key ? <span>{desc ? " ↓" : " ↑"}</span> : null}
                    </button>
                  ) : (
                    label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => {
              const m = metric(c);
              const flow = (m.buy_usd || 0) + (m.sell_usd || 0);
              return (
                <tr key={c.id}>
                  <td>
                    <button
                      className="screener-token"
                      onClick={() => onOpen(c.id)}
                    >
                      <span className="screener-rank">#{i + 1}</span>
                      <span className="market-avatar">
                        {c.symbol.slice(0, 2)}
                      </span>
                      <span>
                        <b>{c.symbol}</b>
                        <em> / {money.unit}</em>
                        <small>{c.name}</small>
                      </span>
                    </button>
                  </td>
                  <td className="screener-cap">
                    {money.compact(c.market_cap)}
                    <small title="Quote-side pool reserve. Market cap is price × circulating supply, not money invested.">
                      {money.compact(c.pool_usd)} pool
                    </small>
                  </td>
                  <td>{money.format(c.price)}</td>
                  <td className="screener-age">
                    {age(c.created_at, state?.server_time || Date.now() / 1000)}
                  </td>
                  <td>{m.txns?.toLocaleString() ?? "—"}</td>
                  <td>{m.volume == null ? "—" : money.compact(m.volume)}</td>
                  <td>{m.traders?.toLocaleString() ?? "—"}</td>
                  {WINDOWS.map((w) => (
                    <td key={w}>
                      <Percent value={c.windows?.[w]?.change} />
                    </td>
                  ))}
                  <td>
                    <div className="screener-flow">
                      <span className="up">{m.buys ?? 0}</span>
                      <span className="down">{m.sells ?? 0}</span>
                    </div>
                    <div className="screener-flow-bar">
                      <i
                        style={{
                          width:
                            (flow ? ((m.buy_usd || 0) / flow) * 100 : 50) + "%",
                        }}
                      />
                    </div>
                  </td>
                  <td>
                    <button
                      className="table-buy"
                      disabled={busy}
                      onClick={() => onBuy(c.id, 50)}
                    >
                      Buy {money.compact(50)}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!rows.length && (
          <p className="empty-market">
            {state
              ? mode === "trending"
                ? "No buying activity in this window yet. Explore All markets."
                : "No markets match your filters."
              : "Connecting to the market…"}
          </p>
        )}
      </div>
      <div className="screener-caption">
        <span>
          {rows.length} markets in the current feed · Live simulated trades ·
          Select a token to open its chart
        </span>
        <span>
          {money.unit === "ETH"
            ? `Simulated ETH · 1 ETH = $${money.rate.toLocaleString()}`
            : "Virtual USD"}
        </span>
      </div>
    </section>
  );
}
export function Activity({ state, selected, me }) {
  const money = useCurrency();
  const usd = money.format;
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
          <button
            className={tab === "positions" ? "active" : ""}
            onClick={() => setTab("positions")}
          >
            Positions
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
      {tab === "positions" ? (
        <div className="token-position-tab">
          {me ? (
            <>
              <div>
                <span>Tokens held</span>
                <b>{(me.holdings[selected] || 0).toLocaleString()}</b>
              </div>
              <div>
                <span>Spot value</span>
                <b>
                  {usd(
                    (me.holdings[selected] || 0) *
                      (state?.coins.find((c) => c.id === selected)?.price || 0),
                  )}
                </b>
              </div>
              <div>
                <span>Available {money.unit}</span>
                <b>{usd(me.cash)}</b>
              </div>
              <a href="/portfolio">View portfolio ↗</a>
            </>
          ) : (
            <p className="muted">Sign in to see your saved position.</p>
          )}
        </div>
      ) : (
        <div className="table-scroll">
          <table className="terminal-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Side</th>
                <th>{money.unit}</th>
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
      )}
      {tab !== "positions" && !trades.length && (
        <p className="empty-market">
          {tab === "mine" && !me
            ? "Sign in to see your executions."
            : "No matching executions in the recent feed."}
        </p>
      )}
    </section>
  );
}
