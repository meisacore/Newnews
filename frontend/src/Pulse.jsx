import React, { useEffect, useRef, useState } from "react";
import { simulationDisplay } from "./marketState";
import PulseColumn from "./PulseColumn";

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
export default function Pulse({ state, feedError, busy, onOpen, onBuy }) {
  const [query, setQuery] = useState(""),
    [quick, setQuick] = useState("50"),
    [tab, setTab] = useState("new"),
    [now, setNow] = useState(Date.now());
  const watchRef = useRef(null);
  const [watchEdges, setWatchEdges] = useState({ left: false, right: false });
  const health = simulationDisplay(state?.simulation);
  useEffect(() => {
    const el = watchRef.current;
    if (!el) return;
    const update = () =>
      setWatchEdges({
        left: el.scrollLeft > 1,
        right: el.scrollLeft + el.clientWidth < el.scrollWidth - 1,
      });
    update();
    el.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, [state?.large_trades]);
  function scrollWatch(direction) {
    watchRef.current?.scrollBy({
      left: direction * 280,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }
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
              : health.status === "paused"
                ? "Simulation paused · restart the backend to resume"
                : health.status === "delayed"
                  ? "Updating market activity…"
                  : remaining
                    ? `Next launch in ${remaining}s`
                    : "Launching next batch…"}
        </span>
      </div>
      {state?.large_trades?.length > 0 && (
        <section className="whale-watch" aria-label="Large trades">
          <div className="whale-watch-title">
            <strong>Whale watch</strong>
            <small>Recent trades $1k+</small>
          </div>
          <div
            className="whale-watch-trades"
            ref={watchRef}
            tabIndex={0}
            aria-label="Recent large trades"
          >
            {state.large_trades.map((t) => (
              <button
                key={t.id}
                disabled={busy}
                onClick={() => onOpen(t.coin)}
                title={t.reason}
              >
                <span className={t.side === "buy" ? "up" : "down"}>
                  {t.side.toUpperCase()} {money(t.amount / 1e6)}
                </span>
                <small>
                  {t.agent_name || "Player"} · {t.persona || "Player trade"}
                </small>
              </button>
            ))}
          </div>
          <div className="watch-arrows">
            <button
              aria-label="Scroll large trades left"
              disabled={!watchEdges.left}
              onClick={() => scrollWatch(-1)}
            >
              ‹
            </button>
            <button
              aria-label="Scroll large trades right"
              disabled={!watchEdges.right}
              onClick={() => scrollWatch(1)}
            >
              ›
            </button>
          </div>
        </section>
      )}
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
        <span>USD balances · No real funds</span>
      </div>
    </section>
  );
}
