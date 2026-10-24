import React, { useEffect, useState } from "react";
import { simulationDisplay } from "./marketState";
import PulseColumn from "./PulseColumn";
import { useCurrency } from "./Currency";

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
export default function Pulse({ state, feedError, busy, onOpen, onBuy }) {
  const money = useCurrency();
  const [query, setQuery] = useState(""),
    [quick, setQuick] = useState("50"),
    [tab, setTab] = useState("new"),
    [now, setNow] = useState(Date.now());
  const health = simulationDisplay(state?.simulation);
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
  const coins = (state?.coins || []).filter((c) => c.in_feed !== false);
  return (
    <section className="pulse" aria-label="Pulse market feed">
      <div className="pulse-toolbar">
        <div className="pulse-title">
          <h1>Pulse</h1>
          <span
            className="feed-status"
            data-status={feedError ? "offline" : health.status}
          >
            <i />
            {feedError
              ? "Feed unavailable"
              : !state
                ? "Connecting"
                : health.label}
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
            Quick buy <span>{money.unit === "USD" ? "$" : "Ξ"}</span>
            <input
              aria-label={"Quick buy " + money.unit + " amount"}
              type="number"
              min={money.unit === "ETH" ? "0.00000001" : "0.01"}
              step="any"
              value={Number(money.fromUsd(quick).toFixed(8))}
              onChange={(e) => setQuick(String(money.toUsd(e.target.value)))}
            />
            <span>{money.unit}</span>
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
              : health.status === "paused"
                ? "Simulation resuming · waiting for market activity"
                : health.status === "delayed"
                  ? "Updating market activity…"
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
        {stages.map((stage) => (
          <PulseColumn
            key={stage.id}
            stage={stage}
            coins={coins}
            count={state?.pulse_counts?.[stage.id] || 0}
            active={tab === stage.id}
            query={query}
            quick={quick}
            now={serverNow}
            busy={busy}
            health={health}
            feedError={feedError}
            onOpen={onOpen}
            onBuy={onBuy}
          />
        ))}
      </div>
      <div className="pulse-footnote">
        <span>SIMULATED MARKET · {state?.total_coins || 0} coins launched</span>
        <span>{money.unit} balances · No real funds</span>
      </div>
    </section>
  );
}
