import React, { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
} from "lightweight-charts";
import "./style.css";
import Pulse from "./Pulse";
import Agents from "./Agents";
import ActivityDrawer from "./ActivityDrawer";
import { useCurrency } from "./Currency";
import { TokenHeader, TokenInfo } from "./TokenWorkspace";
import { Discover, Activity } from "./Terminal";
import { ExchangeHeader, ExchangeFooter, Portfolio } from "./ExchangeChrome";
import "./terminal.css";
import { validateMarketState } from "./marketState";

async function api(path, token, body, signal) {
  const r = await fetch("/api/" + path, {
    cache: "no-store",
    signal,
    headers: {
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { method: "POST", body: JSON.stringify(body) } : {}),
  });
  let data;
  try {
    data = await r.json();
  } catch {
    throw Error(
      "Cannot reach the market API. Start the updated backend on port 8000.",
    );
  }
  if (!r.ok)
    throw Error(
      typeof data.detail === "string" ? data.detail : "Request failed",
    );
  return data;
}
function Chart({ coin, interval, refresh, range }) {
  const money = useCurrency();
  const el = useRef();
  const chart = useRef();
  const series = useRef();
  const volume = useRef();
  const fitted = useRef(false);
  const [error, setError] = useState("");
  const [empty, setEmpty] = useState(true);
  useEffect(() => {
    const c = createChart(el.current, {
      height: 360,
      autoSize: true,
      layout: { background: { color: "#101921" }, textColor: "#90a0ab" },
      grid: {
        vertLines: { color: "#1a2630" },
        horzLines: { color: "#1a2630" },
      },
      timeScale: { timeVisible: true },
      rightPriceScale: { borderColor: "#292d31" },
    });
    chart.current = c;
    series.current = c.addSeries(CandlestickSeries, {
      upColor: "#77d99b",
      downColor: "#ed7d8f",
      borderVisible: false,
      wickUpColor: "#77d99b",
      wickDownColor: "#ed7d8f",
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
  }, [coin, interval, range]);
  useEffect(() => {
    let cancelled = false;
    api(`candles/${coin}?interval=${interval}&range_seconds=${range}`)
      .then((data) => {
        if (cancelled) return;
        setError("");
        setEmpty(!data.length);
        series.current.applyOptions({
          priceFormat: {
            type: "price",
            precision: money.unit === "ETH" ? 12 : 8,
            minMove: money.unit === "ETH" ? 0.000000000001 : 0.00000001,
          },
        });
        series.current.setData(
          data.map((x) => ({
            ...x,
            open: money.fromUsd(x.open),
            high: money.fromUsd(x.high),
            low: money.fromUsd(x.low),
            close: money.fromUsd(x.close),
          })),
        );
        volume.current.setData(
          data.map((x) => ({
            time: x.time,
            value: money.fromUsd(x.volume),
            color: x.close >= x.open ? "#6ad2ac55" : "#ee879355",
          })),
        );
        if (!fitted.current && data.length) {
          if (range === 86400)
            chart.current
              .timeScale()
              .setVisibleLogicalRange({
                from: data.length - 1 - Math.floor(range / interval),
                to: data.length + 3,
              });
          else if (data.length < 40)
            chart.current
              .timeScale()
              .setVisibleLogicalRange({
                from: data.length - 60,
                to: data.length + 4,
              });
          else chart.current.timeScale().fitContent();
          fitted.current = true;
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [coin, interval, refresh, money.unit, range]);
  return (
    <>
      <div className="chart-canvas" ref={el} />
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
function readRoute() {
  const hash = window.location.hash.slice(1);
  if (hash.startsWith("coin/"))
    return { view: "coin", coin: decodeURIComponent(hash.slice(5)) };
  return {
    view: ["pulse", "discover", "trade", "portfolio", "agents"].includes(hash)
      ? hash
      : "pulse",
  };
}
export function App({ auth }) {
  const money = useCurrency();
  const dollars = money.format;
  const [whales, setWhales] = useState(false);
  const previousUnit = useRef(money.unit);
  const [route, setRoute] = useState(readRoute),
    [state, setState] = useState(null),
    [feedError, setFeedError] = useState(""),
    [me, setMe] = useState(null),
    [selected, setSelected] = useState(() => readRoute().coin || ""),
    [interval, setIntervalValue] = useState(60),
    [range, setRange] = useState(7200),
    [period, setPeriod] = useState("24h"),
    [side, setSide] = useState("buy"),
    [amount, setAmount] = useState(() => String(money.fromUsd(50))),
    [quote, setQuote] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [refresh, setRefresh] = useState(0);
  const session = useRef(0);
  const feedRequest = useRef(0);
  const feedSelection = useRef(selected);
  feedSelection.current = selected;
  async function load(signal) {
    if (selected !== feedSelection.current) return;
    const request = ++feedRequest.current;
    try {
      const data = validateMarketState(
        await api(
          "state?selected=" + encodeURIComponent(selected),
          undefined,
          undefined,
          signal,
        ),
      );
      if (
        signal?.aborted ||
        request !== feedRequest.current ||
        selected !== feedSelection.current
      )
        return;
      setFeedError("");
      setState({ ...data, receivedAt: Date.now() });
      setRefresh((v) => v + 1);
    } catch (error) {
      if (
        signal?.aborted ||
        request !== feedRequest.current ||
        selected !== feedSelection.current
      )
        return;
      throw error;
    }
  }
  useEffect(() => {
    let stopped = false,
      timer,
      controller;
    async function poll() {
      controller = new AbortController();
      try {
        await load(controller.signal);
      } catch (error) {
        if (!stopped) setFeedError(error.message);
      }
      // Slow responses must finish before another poll starts. This prevents
      // overlapping snapshots from moving the feed or heartbeat backwards.
      if (!stopped) timer = setTimeout(poll, 3000);
    }
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [selected]);
  useEffect(() => {
    const update = () => {
      const next = readRoute();
      setRoute(next);
      if (next.coin) setSelected(next.coin);
      setQuote(null);
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  function openCoin(id) {
    window.location.hash = "coin/" + encodeURIComponent(id);
  }
  function prepareBuy(id, value) {
    setSide("buy");
    setAmount(String(money.fromUsd(value)));
    openCoin(id);
    if (!auth.authenticated) auth.login();
  }
  useEffect(() => {
    const version = ++session.current;
    setMe(null);
    setQuote(null);
    if (!auth.authenticated) return;
    const updateMe = async () => {
      try {
        const token = await auth.getToken();
        const account = await api("me", token);
        if (session.current === version) setMe(account);
      } catch (e) {
        if (session.current === version) setError(e.message);
      }
    };
    updateMe();
    const timer = setInterval(updateMe, 10000);
    return () => clearInterval(timer);
  }, [auth.authenticated]);
  useEffect(() => {
    setQuote(null);
    setNotice("");
  }, [selected, side, amount]);
  useEffect(() => {
    setNotice("");
  }, [route.view]);
  useEffect(() => {
    if (previousUnit.current !== money.unit) {
      if (side === "buy")
        setAmount((value) =>
          String(
            Number(
              (money.unit === "ETH"
                ? Number(value) / money.rate
                : Number(value) * money.rate
              ).toFixed(money.unit === "ETH" ? 12 : 2),
            ),
          ),
        );
      previousUnit.current = money.unit;
      setQuote(null);
    }
  }, [money.unit]);
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
          ...(side === "buy"
            ? { budget: Math.round(money.toUsd(n) * 1e6) }
            : { qty: n }),
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
          const account = await api("me", token);
          if (version === session.current) setMe(account);
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
    <div className={"app terminal-app view-" + route.view}>
      <ExchangeHeader
        state={state}
        me={me}
        auth={auth}
        route={route}
        selected={selected}
        onOpen={openCoin}
        onWhales={() => setWhales(true)}
      />
      <ActivityDrawer
        open={whales}
        onClose={() => setWhales(false)}
        state={state}
        busy={busy}
        onOpen={openCoin}
      />
      {route.view !== "pulse" && (
        <section className="intro">
          <div>
            <p className="eyebrow">NORX / THE EXCHANGE</p>
            <h1>
              {route.view === "coin"
                ? "Your next move."
                : route.view === "portfolio"
                  ? "Portfolio"
                  : route.view === "agents"
                    ? "Meet the traders."
                    : route.view === "trade"
                      ? "Trade"
                      : "Discover"}
            </h1>
            <p className="muted">
              Your edge starts here. Trade the simulated market in virtual{" "}
              {money.unit}.
            </p>
          </div>
          <div className="condition">
            <span className="dot" />
            {state?.condition || "Connecting"} economy
            <br />
            <small>
              {state?.agents.length || "—"} independent rule-based agents
            </small>
          </div>
        </section>
      )}
      {feedError && (
        <div role="alert" className="error banner">
          Market feed unavailable: {feedError}
        </div>
      )}
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
      {route.view === "agents" && <Agents state={state} />}
      {route.view === "pulse" && (
        <Pulse
          state={state}
          feedError={feedError}
          busy={busy}
          onOpen={openCoin}
          onBuy={prepareBuy}
        />
      )}
      {route.view === "coin" && (
        <a className="back-to-pulse" href="#pulse">
          ← Back to Pulse
        </a>
      )}
      {route.view === "trade" && (
        <p className="market-picker-note">
          Choose a coin below to open its chart and {money.unit} trade ticket.
        </p>
      )}
      {(route.view === "discover" || route.view === "trade") && (
        <Discover
          state={state}
          onOpen={openCoin}
          onBuy={prepareBuy}
          busy={busy}
          picker={route.view === "trade"}
          onWhales={() => setWhales(true)}
        />
      )}
      {route.view === "coin" && coin && (
        <main className="trading-workspace token-workspace">
          <section className="panel token-left">
            <TokenHeader coin={coin} period={period} onPeriod={setPeriod} />
            <div className="token-chart-tools">
              <div
                className="intervals"
                role="group"
                aria-label="Candle interval"
              >
                {[
                  [60, "1m"],
                  [300, "5m"],
                  [900, "15m"],
                  [3600, "1h"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    className={interval === value ? "active" : ""}
                    onClick={() => setIntervalValue(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div
                className="chart-range"
                role="group"
                aria-label="Chart range"
              >
                <button
                  className={range === 7200 ? "active" : ""}
                  onClick={() => setRange(7200)}
                >
                  2h view
                </button>
                <button
                  className={range === 86400 ? "active" : ""}
                  title="Show the last 24 hours of available trades"
                  onClick={() => {
                    setRange(86400);
                    setIntervalValue(300);
                  }}
                >
                  24h view
                </button>
              </div>
              <span>{money.unit} · Candles</span>
            </div>
            <div className="chart-frame">
              <Chart
                coin={selected}
                interval={interval}
                refresh={refresh}
                range={range}
              />
            </div>
            <Activity state={state} selected={selected} me={me} />
          </section>
          <aside className="panel order-ticket">
            <h2>Trade token</h2>
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
            <div className="market-order-label">
              Market order <span>0.3% fee</span>
            </div>
            <div className="ticket-presets">
              {(side === "buy"
                ? money.unit === "ETH"
                  ? [0.01, 0.05, 0.1, 1]
                  : [25, 50, 250, 1000]
                : [25, 50, 75, 100]
              ).map((n) => (
                <button
                  key={n}
                  disabled={busy}
                  onClick={() => {
                    setAmount(
                      String(
                        side === "buy"
                          ? n
                          : Math.floor(
                              ((me?.holdings[selected] || 0) * n) / 100,
                            ),
                      ),
                    );
                    setQuote(null);
                  }}
                >
                  {side === "buy"
                    ? money.unit === "ETH"
                      ? n + " ETH"
                      : "$" + n
                    : n + "%"}
                </button>
              ))}
            </div>
            <label htmlFor="amount">
              {side === "buy"
                ? "Spend virtual " + money.unit
                : "Tokens to sell"}
            </label>
            <div className="input">
              <span>{side === "buy" ? money.unit : coin.symbol}</span>
              <input
                id="amount"
                disabled={busy}
                type="number"
                min={
                  side === "buy"
                    ? money.unit === "ETH"
                      ? ".00000001"
                      : ".01"
                    : "1"
                }
                step={
                  side === "buy"
                    ? money.unit === "ETH"
                      ? ".00000001"
                      : ".01"
                    : "1"
                }
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
            {money.unit === "ETH" && (
              <p className="muted fine">
                Simulated rate: 1 ETH = ${money.rate.toLocaleString()}. No real
                ETH.
              </p>
            )}
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
            <div className="ticket-position">
              <span>Your position</span>
              <strong>
                {(me?.holdings[selected] || 0).toLocaleString()} {coin.symbol}
              </strong>
              <div>
                <span>Spot value</span>
                <b>{dollars((me?.holdings[selected] || 0) * coin.price)}</b>
              </div>
              <div>
                <span>Available {money.unit}</span>
                <b>{me ? dollars(me.cash) : "—"}</b>
              </div>
            </div>
            <TokenInfo coin={coin} />
            <p className="muted fine">
              New accounts receive {money.format(10000)} in virtual funds once.
              Your portfolio is saved when you leave.
            </p>
          </aside>
        </main>
      )}

      {route.view === "portfolio" && (
        <Portfolio me={me} state={state} auth={auth} onOpen={openCoin} />
      )}
      <ExchangeFooter state={state} feedError={feedError} />
    </div>
  );
}
export function PublicApp() {
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
