import React, { useEffect, useRef, useState } from "react";
import { Search, UserRound, ArrowUpRight, X, Command } from "lucide-react";
import { simulationDisplay } from "./marketState";
import { useCurrency } from "./Currency";
import { Waves } from "lucide-react";
export function ExchangeHeader({
  state,
  me,
  auth,
  route,
  selected,
  onOpen,
  onWhales,
}) {
  const money = useCurrency();
  const usd = money.format;
  const [search, setSearch] = useState(false),
    [query, setQuery] = useState("");
  const dialog = useRef(null),
    trigger = useRef(null),
    input = useRef(null);
  useEffect(() => {
    function key(e) {
      if (
        (e.key === "/" || ((e.ctrlKey || e.metaKey) && e.key === "k")) &&
        !["INPUT", "SELECT", "TEXTAREA"].includes(
          document.activeElement.tagName,
        )
      ) {
        e.preventDefault();
        setSearch(true);
      }
    }
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  useEffect(() => {
    if (search) {
      dialog.current.showModal();
      input.current.focus();
    } else if (dialog.current?.open) {
      dialog.current.close();
      trigger.current?.focus();
    }
  }, [search]);
  const results = (state?.coins || [])
    .filter((c) =>
      (c.name + " " + c.symbol + " " + c.id)
        .toLowerCase()
        .includes(query.toLowerCase()),
    )
    .slice(0, 10);
  const equity = me
    ? me.cash +
      (me.positions || []).reduce(
        (v, p) =>
          v +
          p.qty * (state?.coins.find((c) => c.id === p.id)?.price ?? p.price),
        0,
      )
    : null;
  return (
    <>
      <header className="exchange-header">
        <a className="logo" href="/" aria-label="NORX welcome">
          <span className="wordmark">
            NOR<span>X</span>
          </span>
        </a>
        <nav className="world-nav" aria-label="World navigation">
          {[
            ["pulse", "Pulse"],
            ["discover", "Discover"],
            ["trade", "Trade"],
            ["portfolio", "Portfolio"],
            ["agents", "Agents"],
          ].map(([id, label]) => (
            <a
              key={id}
              href={"#" + id}
              className={
                route.view === id ||
                (label === "Trade" && route.view === "coin")
                  ? "selected"
                  : ""
              }
            >
              {label}
            </a>
          ))}
        </nav>
        <button
          className="global-search"
          ref={trigger}
          onClick={() => setSearch(true)}
          aria-label="Search all markets"
        >
          <Search size={14} />
          <span>Search coins or symbol</span>
          <kbd>/</kbd>
        </button>
        <div
          className="currency-switch"
          role="group"
          aria-label="Quote currency"
          title={`Simulated rate: 1 ETH = $${money.rate.toLocaleString()}. No real ETH.`}
        >
          {["USD", "ETH"].map((value) => (
            <button
              key={value}
              aria-pressed={money.unit === value}
              onClick={() => money.setUnit(value)}
            >
              {value}
            </button>
          ))}
        </div>
        <button
          className="whale-trigger"
          aria-label="Open whale watch"
          title="Whale watch"
          onClick={onWhales}
        >
          <Waves size={17} />
        </button>
        <a
          href="#portfolio"
          className="equity-chip"
          title="Cash plus holdings valued at spot prices"
        >
          <span>Equity</span>
          <b>{equity === null ? "—" : usd(equity)}</b>
        </a>
        <div className="account">
          {auth.authenticated ? (
            <>
              <span className="account-cash">
                {me ? usd(me.cash) : "Loading…"}
                <small>virtual {money.unit}</small>
              </span>
              <button onClick={() => auth.logout()}>
                <UserRound size={14} />
                Sign out
              </button>
            </>
          ) : (
            <button disabled={!auth.ready} onClick={() => auth.login()}>
              <UserRound size={14} />
              {auth.label || "Account"}
            </button>
          )}
        </div>
      </header>
      <dialog
        ref={dialog}
        className="search-dialog"
        onCancel={() => setSearch(false)}
        onClick={(e) => {
          if (e.target === dialog.current) setSearch(false);
        }}
      >
        <div className="search-dialog-inner">
          <div className="search-dialog-heading">
            <Search size={18} />
            <input
              ref={input}
              aria-label="Search all tokens"
              placeholder="Search by name, symbol, or coin ID"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button aria-label="Close search" onClick={() => setSearch(false)}>
              <X size={18} />
            </button>
          </div>
          <div className="search-results">
            {results.map((c) => (
              <button
                key={c.id}
                onClick={() => {
                  onOpen(c.id);
                  setSearch(false);
                  setQuery("");
                }}
              >
                <span className="market-avatar">{c.symbol.slice(0, 2)}</span>
                <span>
                  <b>{c.name}</b>
                  <small>{c.symbol}</small>
                </span>
                <span className="search-result-price">
                  {usd(c.price)}
                  <small className={c.change_24h >= 0 ? "up" : "down"}>
                    {c.change_24h.toFixed(2)}%
                  </small>
                </span>
                <ArrowUpRight size={14} />
              </button>
            ))}
            {!results.length && (
              <p className="empty-market">
                {state ? "No matching coins." : "Connecting to the market…"}
              </p>
            )}
          </div>
          <div className="search-hint">
            <Command size={12} /> Search the current market feed{" "}
            <span>Esc to close</span>
          </div>
        </div>
      </dialog>
    </>
  );
}
export function ExchangeFooter({ state, feedError }) {
  const money = useCurrency();
  const health = simulationDisplay(state?.simulation);
  return (
    <footer className="exchange-footer">
      <span
        className={
          feedError ? "down" : health.status === "live" ? "up" : "muted"
        }
      >
        <i className="dot" />
        {feedError ? "Feed unavailable" : health.label}
      </span>
      <span>{state?.total_coins ?? "—"} markets</span>
      <span>{state?.agents.length ?? "—"} agents</span>
      <span className="footer-economy">
        {state?.condition || "Connecting"} economy
      </span>
      <span className="footer-disclaimer">
        Paper trading · Virtual {money.unit} · No real funds
      </span>
      <a href="/">
        NORX <ArrowUpRight size={11} />
      </a>
    </footer>
  );
}
export function Portfolio({ me, state, auth, onOpen }) {
  const money = useCurrency();
  const usd = money.format;
  const positions = (me?.positions || []).map((p) => ({
    ...p,
    price: state?.coins.find((c) => c.id === p.id)?.price ?? p.price,
  }));
  const value = positions.reduce((v, p) => v + p.qty * p.price, 0);
  return (
    <section className="portfolio-workspace">
      <div className="portfolio-summary">
        {[
          ["Account equity", me ? usd(me.cash + value) : "—"],
          ["Available " + money.unit, me ? usd(me.cash) : "—"],
          ["Holdings value", me ? usd(value) : "—"],
          ["Open positions", me ? positions.length : "—"],
        ].map(([label, v]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{v}</strong>
            <small>
              {label === "Holdings value"
                ? "At current spot prices"
                : label === "Account equity"
                  ? "Cash + holdings at spot"
                  : "Virtual trading account"}
            </small>
          </div>
        ))}
      </div>
      <section className="terminal-panel">
        <div className="table-toolbar">
          <h2>
            Positions <span className="column-count">{positions.length}</span>
          </h2>
          <span className="muted">Saved to your account</span>
        </div>
        {!me ? (
          <div className="portfolio-empty">
            <UserRound size={28} />
            <h2>Your portfolio starts here</h2>
            <p>Sign in to continue with your saved balance and positions.</p>
            <button
              className="primary"
              disabled={!auth.ready}
              onClick={() => auth.login()}
            >
              {auth.label || "Sign in"}
            </button>
          </div>
        ) : (
          <>
            <div className="table-scroll">
              <table className="terminal-table">
                <thead>
                  <tr>
                    <th>Token</th>
                    <th>Balance</th>
                    <th>Spot price</th>
                    <th>Spot value</th>
                    <th>Trade</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <button
                          className="market-name"
                          onClick={() => onOpen(p.id)}
                        >
                          <span className="market-avatar">
                            {p.symbol.slice(0, 2)}
                          </span>
                          <span>
                            <b>{p.name}</b>
                            <small>{p.symbol}</small>
                          </span>
                        </button>
                      </td>
                      <td>{p.qty.toLocaleString()}</td>
                      <td>{usd(p.price)}</td>
                      <td>{usd(p.qty * p.price)}</td>
                      <td>
                        <button
                          className="table-buy"
                          onClick={() => onOpen(p.id)}
                        >
                          Open market <ArrowUpRight size={12} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!positions.length && (
              <p className="empty-market">
                No open positions. Discover a coin to make your first trade.
              </p>
            )}
          </>
        )}
        <div className="table-caption">
          Spot values are estimates. Actual sale proceeds depend on liquidity
          and fees.
        </div>
      </section>
      {me && (
        <section className="terminal-panel">
          <div className="table-toolbar">
            <h2>Your recent trades</h2>
            <span className="muted">Latest 50 executions</span>
          </div>
          <div className="table-scroll">
            <table className="terminal-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Token</th>
                  <th>Side</th>
                  <th>Quantity</th>
                  <th>{money.unit}</th>
                </tr>
              </thead>
              <tbody>
                {me.trades.map((t) => (
                  <tr key={t.id}>
                    <td>{new Date(t.ts * 1000).toLocaleString()}</td>
                    <td>
                      <a href={"#coin/" + encodeURIComponent(t.coin)}>
                        {state?.coins.find((c) => c.id === t.coin)?.symbol ||
                          t.coin}
                      </a>
                    </td>
                    <td className={t.side === "buy" ? "up" : "down"}>
                      {t.side.toUpperCase()}
                    </td>
                    <td>{t.qty.toLocaleString()}</td>
                    <td>{usd(t.amount / 1e6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!me.trades.length && (
            <p className="empty-market">
              Your executed trades will appear here.
            </p>
          )}
        </section>
      )}
    </section>
  );
}
