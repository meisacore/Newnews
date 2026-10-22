import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { PrivyProvider, usePrivy } from "@privy-io/react-auth";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
} from "lightweight-charts";
import "./style.css";

const dollars = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: n < 1 ? 5 : 2,
  }).format(n || 0);
async function api(path, token, body) {
  const r = await fetch("/api/" + path, {
    headers: {
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { method: "POST", body: JSON.stringify(body) } : {}),
  });
  const data = await r.json();
  if (!r.ok)
    throw Error(
      typeof data.detail === "string" ? data.detail : "Request failed",
    );
  return data;
}
function Chart({ coin, interval, refresh }) {
  const el = useRef();
  const chart = useRef();
  const series = useRef();
  const volume = useRef();
  const fitted = useRef(false);
  const [error, setError] = useState("");
  const [empty, setEmpty] = useState(true);
  useEffect(() => {
    const c = createChart(el.current, {
      height: 340,
      autoSize: true,
      layout: { background: { color: "#101921" }, textColor: "#90a0ab" },
      grid: {
        vertLines: { color: "#1a2630" },
        horzLines: { color: "#1a2630" },
      },
      timeScale: { timeVisible: true },
      rightPriceScale: { borderColor: "#26343d" },
    });
    chart.current = c;
    series.current = c.addSeries(CandlestickSeries, {
      upColor: "#6ad2ac",
      downColor: "#ee8793",
      borderVisible: false,
      wickUpColor: "#6ad2ac",
      wickDownColor: "#ee8793",
    });
    volume.current = c.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volume.current
      .priceScale()
      .applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    return () => c.remove();
  }, []);
  useEffect(() => {
    fitted.current = false;
  }, [coin, interval]);
  useEffect(() => {
    let cancelled = false;
    api(`candles/${coin}?interval=${interval}`)
      .then((data) => {
        if (cancelled) return;
        setError("");
        setEmpty(!data.length);
        series.current.setData(data);
        volume.current.setData(
          data.map((x) => ({
            time: x.time,
            value: x.volume,
            color: x.close >= x.open ? "#6ad2ac55" : "#ee879355",
          })),
        );
        if (!fitted.current && data.length) {
          chart.current.timeScale().fitContent();
          fitted.current = true;
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [coin, interval, refresh]);
  return (
    <>
      <div ref={el} />
      {error ? (
        <p className="error">{error}</p>
      ) : empty ? (
        <p className="muted">
          Waiting for the first simulated trade. Candles will appear here.
        </p>
      ) : null}
    </>
  );
}
function App({ auth }) {
  const [state, setState] = useState(null),
    [me, setMe] = useState(null),
    [selected, setSelected] = useState("frog"),
    [interval, setIntervalValue] = useState(60),
    [side, setSide] = useState("buy"),
    [amount, setAmount] = useState("50"),
    [quote, setQuote] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [refresh, setRefresh] = useState(0);
  const session = useRef(0);
  async function load() {
    const data = await api("state");
    setState(data);
    setRefresh((v) => v + 1);
  }
  useEffect(() => {
    load().catch((e) => setError(e.message));
    const timer = setInterval(
      () => load().catch((e) => setError(e.message)),
      3000,
    );
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const version = ++session.current;
    setMe(null);
    setQuote(null);
    if (auth.authenticated)
      auth
        .getToken()
        .then((t) => api("me", t))
        .then((a) => {
          if (session.current === version) setMe(a);
        })
        .catch((e) => setError(e.message));
  }, [auth.authenticated]);
  useEffect(() => {
    setQuote(null);
    setNotice("");
  }, [selected, side, amount]);
  const coin = state?.coins.find((c) => c.id === selected);
  async function action() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const version = session.current;
      const token = await auth.getToken();
      if (!quote) {
        const n = Number(amount);
        if (!Number.isFinite(n) || n <= 0)
          throw Error("Enter a positive amount");
        if (side === "sell" && !Number.isInteger(n))
          throw Error("Sell quantity must be a whole number");
        const data = await api("quote", token, {
          coin: selected,
          side,
          ...(side === "buy" ? { budget: Math.round(n * 1e6) } : { qty: n }),
        });
        if (version === session.current) setQuote(data);
      } else {
        const result = await api("trade", token, {
          quote_id: quote.id,
          request_id: quote.id,
        });
        setQuote(null);
        if (version === session.current) {
          setNotice(
            `${result.side === "buy" ? "Bought" : "Sold"} ${result.qty.toLocaleString()} ${result.qty === 1 ? "token" : "tokens"} for ${dollars(result.usd)}.`,
          );
          setMe(await api("me", token));
          await load();
        }
      }
    } catch (e) {
      setError(e.message);
      setQuote(null);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="app">
      <header>
        <a className="logo" href="/">
          NOR<span>X</span>
        </a>
        <span className="tag">A fictional market. Real decisions.</span>
        <div className="account">
          {auth.authenticated ? (
            <>
              <span>
                {me ? dollars(me.cash) : "Loading balance…"}{" "}
                <small>virtual USD</small>
              </span>
              <button onClick={() => auth.logout()}>Sign out</button>
            </>
          ) : (
            <button disabled={!auth.ready} onClick={() => auth.login()}>
              {auth.label || "Sign in"}
            </button>
          )}
        </div>
      </header>
      <div className="disclaimer">
        SIMULATED WORLD · No real money, wallets, or withdrawals{" "}
        {auth.dev && " · LOCAL TEST ACCOUNT"}
      </div>
      <section className="intro">
        <div>
          <p className="eyebrow">NORX / THE EXCHANGE</p>
          <h1>Your next move.</h1>
          <p className="muted">
            Trade fictional coins with virtual dollars in a world that keeps
            moving.
          </p>
        </div>
        <div className="condition">
          <span className="dot" />
          {state?.condition || "Connecting"} economy
          <br />
          <small>30 independent rule-based agents</small>
        </div>
      </section>
      {error && (
        <div role="alert" className="error banner">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="success banner">
          {notice}
        </div>
      )}
      <section className="market-list">
        {state?.coins.map((c) => (
          <button
            className={"coin " + (c.id === selected ? "selected" : "")}
            key={c.id}
            disabled={busy}
            onClick={() => {
              setSelected(c.id);
              setQuote(null);
            }}
          >
            <div>
              <strong>{c.symbol}</strong>
              <small>{c.name}</small>
            </div>
            <div>
              <strong>{dollars(c.price)}</strong>
              <small className={c.change_24h >= 0 ? "up" : "down"}>
                {c.change_24h >= 0 ? "+" : ""}
                {c.change_24h.toFixed(2)}% · 24h
              </small>
            </div>
          </button>
        )) || <p>Connecting to the market…</p>}
      </section>
      {coin && (
        <main>
          <section className="panel">
            <div className="chart-heading">
              <div>
                <h2>
                  {coin.name} <small>{coin.symbol}/USD</small>
                </h2>
                <strong className="price">{dollars(coin.price)}</strong>
              </div>
              <div className="intervals">
                {[
                  [60, "1m"],
                  [300, "5m"],
                  [3600, "1h"],
                ].map(([v, label]) => (
                  <button
                    className={interval === v ? "active" : ""}
                    key={v}
                    onClick={() => setIntervalValue(v)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <Chart coin={selected} interval={interval} refresh={refresh} />
            <div className="stats">
              <div>
                Circulating market cap
                <strong>{dollars(coin.market_cap)}</strong>
              </div>
              <div>
                24h volume<strong>{dollars(coin.volume_24h)}</strong>
              </div>
              <div>
                Circulating supply
                <strong>{coin.circulating_supply.toLocaleString()}</strong>
              </div>
            </div>
            <p className="muted fine">
              Candles show fee-exclusive trade prices and USD volume. The
              current price is the pool spot price. Market cap is a valuation,
              not cash invested.
            </p>
          </section>
          <aside className="panel">
            <h2>Make your move</h2>
            <div className="tabs">
              {["buy", "sell"].map((s) => (
                <button
                  className={s === side ? "active" : ""}
                  disabled={busy}
                  onClick={() => setSide(s)}
                  key={s}
                >
                  {s}
                </button>
              ))}
            </div>
            <label htmlFor="amount">
              {side === "buy" ? "Spend virtual USD" : "Tokens to sell"}
            </label>
            <div className="input">
              <span>{side === "buy" ? "$" : coin.symbol}</span>
              <input
                id="amount"
                disabled={busy}
                type="number"
                min={side === "buy" ? ".01" : "1"}
                step={side === "buy" ? ".01" : "1"}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
            <p className="muted">
              Held: {(me?.holdings[selected] || 0).toLocaleString()}{" "}
              {coin.symbol}
            </p>
            {quote && (
              <div className="quote">
                <strong>
                  {quote.qty.toLocaleString()} {coin.symbol} ·{" "}
                  {dollars(quote.usd)}
                </strong>
                <p>Fee included. Quote expires in 30 seconds.</p>
                <p>
                  {side === "buy"
                    ? "Your cost cannot exceed this quote."
                    : "Minimum proceeds: " + dollars(quote.usd * 0.99)}
                </p>
              </div>
            )}
            {auth.authenticated ? (
              <button
                className="primary"
                disabled={busy || !me}
                onClick={action}
              >
                {busy
                  ? "Working…"
                  : quote
                    ? "Confirm " + side
                    : "Preview " + side}
              </button>
            ) : (
              <button
                className="primary"
                disabled={!auth.ready}
                onClick={() => auth.login()}
              >
                {auth.label || "Sign in to trade"}
              </button>
            )}
            <p className="muted fine">
              New accounts receive $10,000 virtual USD once. Your portfolio is
              saved when you leave.
            </p>
          </aside>
        </main>
      )}
      <section className="bottom">
        <div className="panel">
          <h2>Your portfolio</h2>
          {!me ? (
            <p className="muted">Sign in to load your saved holdings.</p>
          ) : (
            <>
              <div className="portfolio-line">
                <span>Virtual USD</span>
                <strong>{dollars(me.cash)}</strong>
              </div>
              {state?.coins.map((c) => (
                <div className="portfolio-line" key={c.id}>
                  <span>
                    {c.symbol} · {(me.holdings[c.id] || 0).toLocaleString()}{" "}
                    tokens
                  </span>
                  <strong>{dollars((me.holdings[c.id] || 0) * c.price)}</strong>
                </div>
              ))}
              <p className="muted fine">
                Holding values use spot prices. Actual sale proceeds depend on
                liquidity and fees.
              </p>
              <h3>Your recent trades</h3>
              {me.trades.slice(0, 8).map((t) => (
                <div className="trade" key={t.id}>
                  <span>
                    {t.side} {t.qty.toLocaleString()} {t.coin}
                  </span>
                  <span>{dollars(t.amount / 1e6)}</span>
                </div>
              ))}
            </>
          )}
        </div>
        <div className="panel">
          <h2>World activity</h2>
          <p className="muted fine">
            Agents have finite budgets and different strategies, wealth,
            patience, and risk limits.
          </p>
          {state?.trades.slice(0, 10).map((t) => (
            <div className="trade" key={t.id}>
              <div>
                <span className={t.side === "buy" ? "up" : "down"}>
                  {t.side.toUpperCase()}
                </span>{" "}
                {t.qty.toLocaleString()} {t.coin}
                <small>
                  {t.account.startsWith("agent-") ? t.account : "Player"} ·{" "}
                  {new Date(t.ts * 1000).toLocaleTimeString()}
                </small>
              </div>
              <span>{dollars(t.amount / 1e6)}</span>
            </div>
          ))}
        </div>
      </section>
      <footer>
        All assets, balances, and market activity are fictional. No deposits or
        withdrawals.
      </footer>
    </div>
  );
}
function PrivyApp() {
  const p = usePrivy();
  return (
    <App
      auth={{
        ready: p.ready,
        authenticated: p.authenticated,
        login: p.login,
        logout: p.logout,
        getToken: p.getAccessToken,
      }}
    />
  );
}
function PublicApp() {
  const [dev, setDev] = useState(false),
    [signed, setSigned] = useState(false);
  useEffect(() => {
    api("config")
      .then((c) => setDev(c.dev_auth))
      .catch(() => {});
  }, []);
  return (
    <App
      auth={{
        ready: dev,
        authenticated: signed,
        dev,
        label: dev
          ? "Enter local test account"
          : "Login awaiting configuration",
        login: () => setSigned(true),
        logout: () => setSigned(false),
        getToken: async () => "local-demo",
      }}
    />
  );
}
const id = import.meta.env.VITE_PRIVY_APP_ID;
createRoot(document.getElementById("root")).render(
  id ? (
    <PrivyProvider
      appId={id}
      config={{
        loginMethods: ["email", "google"],
        embeddedWallets: {
          ethereum: { createOnLogin: "off" },
          solana: { createOnLogin: "off" },
          showWalletUIs: false,
        },
        appearance: { theme: "dark", accentColor: "#c9b48c" },
      }}
    >
      <PrivyApp />
    </PrivyProvider>
  ) : (
    <PublicApp />
  ),
);
