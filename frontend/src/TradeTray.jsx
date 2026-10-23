import React, { useState } from "react";

export function useTradeTray() {
  const [size, setSize] = useState(() =>
    Math.max(
      20,
      Math.min(65, Number(localStorage.getItem("norx.chartSize")) || 42),
    ),
  );
  const [expanded, setExpanded] = useState(false);
  function resize(value) {
    const next = Math.max(20, Math.min(65, value));
    setSize(next);
    localStorage.setItem("norx.chartSize", String(next));
  }
  function drag(e) {
    e.preventDefault();
    const start = e.clientY,
      initial = size;
    const height = e.currentTarget.closest(".token-left").clientHeight;
    e.currentTarget.setPointerCapture(e.pointerId);
    const el = e.currentTarget;
    const move = (event) => {
      setExpanded(false);
      resize(initial + ((event.clientY - start) / height) * 100);
    };
    const end = () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", end);
      el.removeEventListener("pointercancel", end);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
  }
  const control = (
    <div className="tray-controls">
      <div
        role="separator"
        tabIndex={0}
        aria-label="Resize trade tray"
        aria-orientation="horizontal"
        aria-valuemin={20}
        aria-valuemax={65}
        aria-valuenow={size}
        onPointerDown={drag}
        onKeyDown={(e) => {
          if (["ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) {
            e.preventDefault();
            setExpanded(false);
            resize(
              e.key === "Home"
                ? 20
                : e.key === "End"
                  ? 65
                  : size + (e.key === "ArrowUp" ? -5 : 5),
            );
          }
        }}
      >
        <span />
      </div>
      <button aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
        {expanded ? "↓ Restore chart" : "↑ Expand trades"}
      </button>
    </div>
  );
  return {
    control,
    style: { "--chart-size": expanded ? "90px" : `${size}dvh` },
  };
}
