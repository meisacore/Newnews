import React, { useEffect, useState } from "react";

const compact = (n) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n || 0);
const money = (n) => "$" + compact(n);
const stages = [
  {
    id: "new",
    title: "New pairs",
    icon: "✧",
    note: "Fresh launches · under 70% activity",
  },
  {
    id: "stretch",
    title: "Final stretch",
    icon: "◈",
    note: "70–100% of the activity milestone",
  },
  {
    id: "migrated",
    title: "Migrated",
    icon: "✦",
    note: "Established · activity milestone reached. Same AMM; no chain migration.",
  },
];
function age(created, now) {
  const seconds = Math.max(0, Math.floor(now / 1000 - created));
  if (seconds < 60) return seconds + "s";
  if (seconds < 3600) return Math.floor(seconds / 60) + "m";
  return Math.floor(seconds / 3600) + "h";
}
export default function Pulse({ state, feedError, busy, onOpen, onBuy }) {
  const [query, setQuery] = useState(""),
    [quick, setQuick] = useState("50"),
    [tab, setTab] = useState("new"),
    [sorts, setSorts] = useState({}),
    [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const serverNow = state
    ? state.server_time + Math.max(0, now - state.receivedAt) / 1000
    : now / 1000;
  const remaining = state
    ? Math.max(0, Math.ceil(state.next_launch_at - serverNow))
    : 0;
  const coins = (state?.coins || [])
    .filter((c) => c.in_feed !== false)
    .filter((c) =>
      (c.name + " " + c.symbol).toLowerCase().includes(query.toLowerCase()),
    );
  return (
    <section className="pulse" aria-label="Pulse market feed">
      <div className="pulse-toolbar">
        <div className="pulse-title">
          <h1>Pulse</h1>
          <span className="feed-status">
            <i />
            {feedError
              ? "Feed unavailable"
              : !state
                ? "Connecting"
                : state.simulation.running
                  ? "Live simulation"
                  : "Simulation paused"}
          </span>
        </div>
        <div className="pulse-controls">
          <input
            aria-label="Search coins"
            placeholder="Search coins…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <label className="quick-label">
            Quick buy <span>$</span>
            <input
              aria-label="Quick buy USD amount"
              type="number"
              min="0.01"
              step="0.01"
              value={quick}
              onChange={(e) => setQuick(e.target.value)}
            />
            <span>USD</span>
          </label>
        </div>
      </div>
      <div className="launch-strip">
        <span>
          <i className="dot" />
          <strong>5 random coins every minute</strong> · Each with its own
          liquidity and chart
        </span>
        <span role="timer">
          {feedError
            ? "Market feed unavailable"
            : !state
              ? "Connecting to the market…"
              : !state.simulation.running
                ? "Simulation paused · restart the backend to resume"
                : remaining
                  ? `Next launch in ${remaining}s`
                  : "Launching next batch…"}
        </span>
      </div>
      <div className="pulse-mobile-tabs">
        {stages.map((s) => (
          <button
            key={s.id}
            className={tab === s.id ? "active" : ""}
            onClick={() => setTab(s.id)}
          >
            {s.title} <small>{state?.pulse_counts?.[s.id] || 0}</small>
          </button>
        ))}
      </div>
      <div className="pulse-columns">
        {stages.map((s) => {
          const list = coins
            .filter((c) => c.stage === s.id)
            .sort((a, b) =>
              sorts[s.id] === "volume"
                ? b.volume_24h - a.volume_24h
                : sorts[s.id] === "cap"
                  ? b.market_cap - a.market_cap
                  : b.created_at - a.created_at || b.id.localeCompare(a.id),
            );
          return (
            <section
              key={s.id}
              className={
                "pulse-column " + (tab === s.id ? "mobile-active" : "")
              }
              aria-label={s.title}
            >
              <div className="pulse-column-header">
                <div>
                  <span className={"stage-icon " + s.id}>{s.icon}</span>
                  <h2 title={s.note}>{s.title}</h2>
                  <span className="column-count">
                    {state?.pulse_counts?.[s.id] || 0}
                  </span>
                </div>
                <select
                  aria-label={`Sort ${s.title}`}
                  value={sorts[s.id] || "newest"}
                  onChange={(e) =>
                    setSorts({ ...sorts, [s.id]: e.target.value })
                  }
                >
                  <option value="newest">Newest</option>
                  <option value="volume">Volume</option>
                  <option value="cap">Market cap</option>
                </select>
              </div>
              <div className="pulse-scroll">
                {list.length ? (
                  list.map((c) => (
                    <article className="pulse-card" key={c.id}>
                      <button
                        disabled={busy}
                        className="pulse-open"
                        aria-label={`Open ${c.name} ${c.symbol}`}
                        onClick={() => onOpen(c.id)}
                      >
                        <div className="pulse-card-top">
                          <div
                            className="coin-art"
                            style={{
                              "--coin-hue":
                                [...c.id].reduce(
                                  (n, ch) => n + ch.charCodeAt(0) * 17,
                                  0,
                                ) % 360,
                            }}
                          >
                            <span>{c.symbol.slice(0, 2)}</span>
                            <i>✦</i>
                          </div>
                          <div className="pulse-identity">
                            <strong>{c.name}</strong>
                            <span>{c.symbol}</span>
                            <small>
                              {c.id} <b>·</b>{" "}
                              {age(c.created_at, serverNow * 1000)} ago
                            </small>
                          </div>
                          <span
                            className={
                              "pulse-change " +
                              (c.change_24h >= 0 ? "up" : "down")
                            }
                          >
                            {c.change_24h >= 0 ? "+" : ""}
                            {c.change_24h.toFixed(1)}%
                          </span>
                        </div>
                        <div className="pulse-metrics">
                          <div>
                            <small>MCAP</small>
                            <strong>{money(c.market_cap)}</strong>
                          </div>
                          <div>
                            <small>VOL 24H</small>
                            <strong>{money(c.volume_24h)}</strong>
                          </div>
                          <div>
                            <small>TXNS</small>
                            <strong>{compact(c.txns)}</strong>
                          </div>
                          <div>
                            <small>HOLDERS</small>
                            <strong>{compact(c.holders)}</strong>
                          </div>
                        </div>
                        <div
                          className="pulse-progress"
                          title="Cumulative traded USD divided by the coin's starting pool USD"
                        >
                          <span>ACTIVITY</span>
                          <div>
                            <i style={{ width: c.progress + "%" }} />
                          </div>
                          <span>{c.progress.toFixed(0)}%</span>
                        </div>
                      </button>
                      <div className="pulse-card-foot">
                        <span>
                          Virtual USD <i>·</i> AMM
                        </span>
                        <button
                          disabled={
                            busy ||
                            !Number.isFinite(Number(quick)) ||
                            Number(quick) <= 0
                          }
                          aria-label={`Prepare ${quick} USD buy of ${c.symbol}`}
                          onClick={() => onBuy(c.id, quick)}
                        >
                          ϟ Buy <strong>${quick}</strong>
                        </button>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="pulse-empty">
                    <span>{s.icon}</span>
                    <strong>
                      {query
                        ? "No matching coins"
                        : s.id === "new"
                          ? "Waiting for the next launch"
                          : "The world is just getting started"}
                    </strong>
                    <p>
                      {s.id === "new"
                        ? "Five new coins arrive each minute while the worker runs."
                        : s.note}
                    </p>
                  </div>
                )}
              </div>
              <div className="column-foot">
                {list.length} displayed
                {(state?.pulse_counts?.[s.id] || 0) > 60
                  ? " · latest 60"
                  : ""}{" "}
                <span>●</span>{" "}
                {feedError
                  ? "Offline"
                  : state?.simulation.running
                    ? "Live"
                    : "Paused"}
              </div>
            </section>
          );
        })}
      </div>
      <div className="pulse-footnote">
        <span>SIMULATED MARKET · {state?.total_coins || 0} coins launched</span>
        <span>USD balances · No real funds</span>
      </div>
    </section>
  );
}
