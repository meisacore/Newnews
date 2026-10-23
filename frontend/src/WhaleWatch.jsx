import React, { useEffect, useRef, useState } from "react";
import { useCurrency } from "./Currency";
export default function WhaleWatch({ state, busy, onOpen }) {
  const currency = useCurrency();
  const money = currency.compact;
  const watchRef = useRef(null);
  const [watchEdges, setWatchEdges] = useState({ left: false, right: false });
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
  if (!state?.large_trades?.length) return null;
  return (
    <section className="whale-watch" aria-label="Large trades">
      <div className="whale-watch-title">
        <strong>Whale watch</strong>
        <small>Recent trades {currency.compact(1000)}+</small>
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
            <small className="whale-market">
              {state?.screener?.find((c) => c.id === t.coin)?.symbol ||
                state?.coins?.find((c) => c.id === t.coin)?.symbol ||
                t.coin}{" "}
              · {new Date(t.ts * 1000).toLocaleTimeString()}
            </small>
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
  );
}
