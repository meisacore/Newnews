import React from "react";
import { TrendingUp, ArrowUpRight } from "lucide-react";
const compact = (n) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n || 0);
export default function HotMarkets({ state, onOpen }) {
  const rows = state?.trending || [];
  return (
    <section className="hot-markets" aria-label="Trending coins">
      <div className="hot-markets-label">
        <strong>
          <TrendingUp size={13} /> Trending
        </strong>
        <small>Buying activity · 5m</small>
      </div>
      <div className="hot-market-scroll">
        {rows.map((c, i) => (
          <button
            key={c.id}
            aria-label={"Open trending " + c.name}
            onClick={() => onOpen(c.id)}
          >
            <span className="hot-rank">{i + 1}</span>
            <span>
              <b>{c.symbol}</b>
              <small>
                {c.buyers_5m} buyers · {c.buys_5m} buys
              </small>
            </span>
            <span className="hot-flow up">
              ${compact(c.buy_usd_5m)}
              <small>buy USD</small>
            </span>
          </button>
        ))}
        {!rows.length && (
          <p className="muted">
            No buys in the last five minutes. Rankings appear as trades execute.
          </p>
        )}
      </div>
      <a href="#discover">
        Explore <ArrowUpRight size={11} />
      </a>
    </section>
  );
}
