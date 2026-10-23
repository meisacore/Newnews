import React, { useEffect, useRef, useState } from "react";
import { BUY_PRESETS, filterPulseRows, sortPulseRows } from "./pulseLogic";
const compact = (n) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n || 0);
const money = (n) => "$" + compact(n);
function age(created, now) {
  const n = Math.max(0, Math.floor(now - created));
  return n < 60
    ? n + "s"
    : n < 3600
      ? Math.floor(n / 60) + "m"
      : Math.floor(n / 3600) + "h";
}
function preferences(id) {
  try {
    const saved = JSON.parse(
      localStorage.getItem("norx.pulse." + id) || "null",
    );
    if (saved && typeof saved === "object")
      return {
        sort: ["newest", "volume", "cap"].includes(saved.sort)
          ? saved.sort
          : "newest",
        buy: BUY_PRESETS.includes(saved.buy) ? saved.buy : null,
        filters:
          saved.filters && typeof saved.filters === "object"
            ? saved.filters
            : {},
      };
  } catch {}
  return { sort: "newest", buy: null, filters: {} };
}
const fields = [
  ["minCap", "Min market cap · USD"],
  ["maxCap", "Max market cap · USD"],
  ["minVolume", "Min 24h volume · USD"],
  ["minHolders", "Min holders"],
  ["maxAge", "Max age · minutes"],
];
export default function PulseColumn({
  stage,
  coins,
  count,
  active,
  query,
  quick,
  now,
  busy,
  health,
  feedError,
  onOpen,
  onBuy,
}) {
  const [settings, setSettings] = useState(() => preferences(stage.id)),
    [showFilters, setShowFilters] = useState(false),
    [mode, setMode] = useState("auto"),
    [hovered, setHovered] = useState(false),
    [scrollHold, setScrollHold] = useState(false);
  const snapshot = useRef([]),
    scrollTimer = useRef(),
    lastQuick = useRef(quick);
  const liveRows = sortPulseRows(
    coins.filter((c) => c.stage === stage.id),
    settings.sort,
  );
  const isHeld =
    mode === "held" || (mode === "auto" && (hovered || scrollHold));
  const rows = filterPulseRows(
    isHeld ? snapshot.current : liveRows,
    query,
    settings.filters,
    now,
  );
  const candidates = filterPulseRows(liveRows, query, settings.filters, now);
  const ids = new Set(snapshot.current.map((c) => c.id));
  const pending = isHeld ? candidates.filter((c) => !ids.has(c.id)).length : 0;
  const buy = settings.buy ?? Number(quick);
  const filterCount = Object.values(settings.filters).filter(
    (x) => x !== "" && x != null,
  ).length;
  useEffect(() => {
    try {
      localStorage.setItem("norx.pulse." + stage.id, JSON.stringify(settings));
    } catch {}
  }, [stage.id, settings]);
  useEffect(() => {
    if (lastQuick.current !== quick) {
      lastQuick.current = quick;
      setSettings((s) => ({ ...s, buy: null }));
    }
  }, [quick]);
  useEffect(() => () => clearTimeout(scrollTimer.current), []);
  function capture() {
    if (!isHeld) snapshot.current = liveRows;
  }
  function holdScroll() {
    if (mode !== "auto") return;
    capture();
    setScrollHold(true);
    clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => setScrollHold(false), 1400);
  }
  function toggleHold() {
    if (mode === "held") {
      setMode("live");
      setScrollHold(false);
    } else {
      capture();
      setMode("held");
    }
  }
  function resumeArrivals() {
    setMode("live");
    setScrollHold(false);
  }
  function changeSort(value) {
    if (isHeld) snapshot.current = sortPulseRows(snapshot.current, value);
    setSettings((s) => ({ ...s, sort: value }));
  }
  return (
    <section
      className={"pulse-column " + (active ? "mobile-active" : "")}
      aria-label={stage.title}
      onMouseEnter={() => {
        capture();
        setHovered(true);
      }}
      onMouseLeave={() => {
        setHovered(false);
        if (mode === "live") setMode("auto");
      }}
    >
      <div className="pulse-column-header">
        <div>
          <span className={"stage-icon " + stage.id}>{stage.icon}</span>
          <h2 title={stage.note}>{stage.title}</h2>
          <span className="column-count">{count}</span>
        </div>
        <select
          aria-label={"Sort " + stage.title}
          value={settings.sort}
          onChange={(e) => changeSort(e.target.value)}
        >
          <option value="newest">Newest</option>
          <option value="volume">Volume</option>
          <option value="cap">Market cap</option>
        </select>
      </div>
      <div className="column-tools">
        <div className="column-presets">
          {BUY_PRESETS.map((value, index) => (
            <button
              key={value}
              className={buy === value ? "selected" : ""}
              aria-label={`Use ${value} USD preset for ${stage.title}`}
              aria-pressed={buy === value}
              title={"Prepare a $" + value + " virtual USD buy"}
              onClick={() => setSettings((s) => ({ ...s, buy: value }))}
            >
              P{index + 1}
              <small>${value}</small>
            </button>
          ))}
        </div>
        <div className="column-options">
          <button
            aria-label={"Filters for " + stage.title}
            aria-expanded={showFilters}
            className={filterCount ? "has-filters" : ""}
            onClick={() => setShowFilters(!showFilters)}
          >
            Filters{filterCount ? " · " + filterCount : ""}
          </button>
          <button
            aria-label={
              (mode === "held" ? "Resume" : "Hold") +
              " arrivals in " +
              stage.title
            }
            title="Hold this column’s cards and displayed figures. The simulation and trade quotes stay live."
            onClick={toggleHold}
          >
            <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
              {mode === "held" ? (
                <path d="M3 1L10 6 3 11Z" fill="currentColor" />
              ) : (
                <path d="M3 2v8M8 2v8" stroke="currentColor" strokeWidth="2" />
              )}
            </svg>
          </button>
        </div>
        {showFilters && (
          <div
            className="column-filters"
            role="region"
            aria-label={stage.title + " filters"}
          >
            <div className="filter-heading">
              <strong>Filter this column</strong>
              <button
                onClick={() => setSettings((s) => ({ ...s, filters: {} }))}
              >
                Clear
              </button>
            </div>
            <div className="filter-fields">
              {fields.map(([key, label]) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    min="0"
                    step={key === "minHolders" ? "1" : "any"}
                    aria-label={label + " for " + stage.title}
                    placeholder="Any"
                    value={settings.filters[key] ?? ""}
                    onChange={(e) =>
                      setSettings((s) => ({
                        ...s,
                        filters: { ...s.filters, [key]: e.target.value },
                      }))
                    }
                  />
                </label>
              ))}
            </div>
          </div>
        )}
      </div>
      <div className={"column-held " + (isHeld ? "is-held" : "")}>
        <span>
          {isHeld
            ? "Arrivals held" + (pending ? " · " + pending + " new" : "")
            : "Live arrivals"}
        </span>
        {isHeld ? (
          <button
            onClick={resumeArrivals}
            aria-label={"Resume " + stage.title + " feed"}
          >
            Resume
          </button>
        ) : (
          <span>Real-time cards</span>
        )}
      </div>
      <div
        className="pulse-scroll"
        onScroll={holdScroll}
        onTouchStart={holdScroll}
      >
        {rows.length ? (
          rows.map((c) => (
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
                      {c.id} <b>·</b> {age(c.created_at, now)} ago
                    </small>
                  </div>
                  <span
                    className={
                      "pulse-change " + (c.change_24h >= 0 ? "up" : "down")
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
                  disabled={busy || !Number.isFinite(buy) || buy <= 0}
                  aria-label={`Prepare ${buy} USD buy of ${c.symbol}`}
                  onClick={() => onBuy(c.id, buy)}
                >
                  ϟ Buy <strong>${buy}</strong>
                </button>
              </div>
            </article>
          ))
        ) : (
          <div className="pulse-empty">
            <span>{stage.icon}</span>
            <strong>
              {query || filterCount
                ? "No matching coins"
                : stage.id === "new"
                  ? "Waiting for the next launch"
                  : "The world is just getting started"}
            </strong>
            <p>
              {query || filterCount
                ? "Adjust this column’s filters or your search."
                : stage.note}
            </p>
          </div>
        )}
      </div>
      <div className="column-foot">
        {rows.length} displayed{count > 60 ? " · latest 60" : ""} <span>●</span>{" "}
        {feedError
          ? "Offline"
          : health.status === "delayed"
            ? "Updating"
            : health.status === "live"
              ? "Live"
              : "Paused"}
        {isHeld && " · arrivals held"}
      </div>
    </section>
  );
}
