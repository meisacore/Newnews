import React, { useState } from "react";
const usd = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format((n || 0) / 1e6);
export default function Agents({ state }) {
  const [query, setQuery] = useState(""),
    [page, setPage] = useState(0);
  const population = [...(state?.agents || [])].sort((a, b) => b.cash - a.cash);
  const matching = population.filter((a) =>
    (a.name + " " + a.personality + " " + a.id)
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const pages = Math.max(1, Math.ceil(matching.length / 40));
  const current = Math.min(page, pages - 1);
  const agents = matching.slice(current * 40, current * 40 + 40);
  return (
    <section className="agents-page" aria-label="Agent population">
      <div className="agent-summary">
        <div>
          <small>INDEPENDENT TRADERS</small>
          <strong>{population.length}</strong>
        </div>
        <div>
          <small>AVAILABLE AGENT USD</small>
          <strong>{usd(population.reduce((sum, a) => sum + a.cash, 0))}</strong>
        </div>
        <div>
          <small>BIGGEST AGENT BUY</small>
          <strong>
            {usd(Math.max(0, ...population.map((a) => a.biggest_buy || 0)))}
          </strong>
        </div>
      </div>
      <p className="muted">
        Wealth and judgment vary. Patient investors check perceived value and
        execution costs. Gamblers and reckless whales can chase hype, overpay,
        change their minds, and lose virtual USD. No strategy is guaranteed to
        win.
      </p>
      <div className="agent-browser">
        <input
          aria-label="Search traders"
          placeholder="Search traders or personalities…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
        />
        <span>
          {matching.length.toLocaleString()} traders · Page {current + 1} of{" "}
          {pages}
        </span>
        <button disabled={current === 0} onClick={() => setPage(current - 1)}>
          Previous
        </button>
        <button
          disabled={current + 1 >= pages}
          onClick={() => setPage(current + 1)}
        >
          Next
        </button>
      </div>
      <div className="agent-grid">
        {agents.map((a) => (
          <article
            className={
              "agent-card " + (a.disciplined ? "disciplined" : "speculative")
            }
            key={a.id}
          >
            <div className="agent-heading">
              <div>
                <h2>{a.name || a.id}</h2>
                <span>{a.personality || a.strategy}</span>
              </div>
              <span className="agent-badge">
                {a.disciplined ? "Disciplined" : "Speculative"}
              </span>
            </div>
            <strong className="agent-cash">
              {usd(a.cash)} <small>available virtual USD</small>
            </strong>
            <div className="agent-facts">
              <div>
                <small>Trades</small>
                <strong>{a.trades || 0}</strong>
              </div>
              <div>
                <small>Biggest buy</small>
                <strong>
                  {a.biggest_buy ? usd(a.biggest_buy) : "No buys yet"}
                </strong>
              </div>
              <div>
                <small>Exposure limit / coin</small>
                <strong>{Math.round(a.risk * 100)}%</strong>
              </div>
            </div>
            <p>
              {a.starting_cash
                ? `${usd(a.starting_cash)} initial grant · funded once`
                : "Original trader · existing balance retained"}
            </p>
          </article>
        ))}
      </div>
      <p className="muted fine">
        All agents trade against the same liquidity as players. Large orders can
        move prices sharply. Exposure values use executable liquidation
        estimates; individual estimates do not promise that everyone can exit at
        once.
      </p>
    </section>
  );
}
