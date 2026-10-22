import React from "react";
const usd = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format((n || 0) / 1e6);
export default function Agents({ state }) {
  const agents = [...(state?.agents || [])].sort((a, b) => b.cash - a.cash);
  return (
    <section className="agents-page" aria-label="Agent population">
      <div className="agent-summary">
        <div>
          <small>INDEPENDENT TRADERS</small>
          <strong>{agents.length}</strong>
        </div>
        <div>
          <small>AVAILABLE AGENT USD</small>
          <strong>{usd(agents.reduce((sum, a) => sum + a.cash, 0))}</strong>
        </div>
        <div>
          <small>BIGGEST AGENT BUY</small>
          <strong>
            {usd(Math.max(0, ...agents.map((a) => a.biggest_buy || 0)))}
          </strong>
        </div>
      </div>
      <p className="muted">
        Wealth and judgment vary. Patient investors check perceived value and
        execution costs. Gamblers and reckless whales can chase hype, overpay,
        change their minds, and lose virtual USD. No strategy is guaranteed to
        win.
      </p>
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
