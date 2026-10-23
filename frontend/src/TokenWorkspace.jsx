import React, { useState } from "react";
import { Copy, Check } from "lucide-react";
import { useCurrency } from "./Currency";
export function TokenHeader({ coin, period, onPeriod }) {
  const money = useCurrency();
  const [copied, setCopied] = useState(false);
  const m = coin.windows?.[period] || {};
  async function copy() {
    try {
      await navigator.clipboard.writeText(coin.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="token-market-header">
      <div className="token-heading-identity">
        <span className="market-avatar">{coin.symbol.slice(0, 2)}</span>
        <div>
          <h2>{coin.name}</h2>
          <small>
            {coin.symbol} / {money.unit}
            <button
              aria-label="Copy token ID"
              title={copied ? "Copied" : coin.id}
              onClick={copy}
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
            </button>
          </small>
        </div>
      </div>
      <div className="token-header-price">
        <strong>{money.format(coin.price)}</strong>
        <small>
          Liquidity <b>{money.compact(coin.pool_usd)}</b>
        </small>
      </div>
      <div
        className="token-periods"
        role="group"
        aria-label="Token statistics window"
      >
        {["5m", "1h", "6h", "24h"].map((w) => (
          <button
            key={w}
            className={w === period ? "active" : ""}
            onClick={() => onPeriod(w)}
          >
            {w}
          </button>
        ))}
      </div>
      <div className="token-window-metrics">
        {[
          [
            "Change",
            m.change == null
              ? "—"
              : (m.change >= 0 ? "+" : "") + m.change.toFixed(2) + "%",
            m.change >= 0 ? "up" : "down",
          ],
          ["Vol", m.volume == null ? "—" : money.compact(m.volume)],
          ["Buys", m.buys?.toLocaleString() ?? "—"],
          ["Sells", m.sells?.toLocaleString() ?? "—"],
          [
            "Net buy",
            m.buy_usd == null ? "—" : money.compact(m.buy_usd - m.sell_usd),
            m.buy_usd >= m.sell_usd ? "up" : "down",
          ],
        ].map(([label, value, color]) => (
          <div key={label}>
            <span>{label}</span>
            <b className={color || ""}>{value}</b>
          </div>
        ))}
      </div>
    </div>
  );
}
export function TokenInfo({ coin }) {
  const money = useCurrency();
  return (
    <section className="token-info">
      <h3>Token info</h3>
      {[
        ["Total supply", coin.total_supply?.toLocaleString() ?? "—"],
        ["Circulating", coin.circulating_supply.toLocaleString()],
        ["Market cap", money.format(coin.market_cap)],
        ["FDV", money.format(coin.fdv)],
        ["Liquidity", money.format(coin.pool_usd)],
        ["Holders", coin.holders.toLocaleString()],
        ["Stage", coin.stage],
      ].map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <b>{value}</b>
        </div>
      ))}
      <p title={coin.id}>{coin.id}</p>
    </section>
  );
}
