import React, { useRef } from "react";

const worlds = [
  [
    "balanced",
    "Balanced",
    "Mixed sentiment and a steady pace. A good place to learn.",
  ],
  ["bull", "Bull run", "More buying interest, profit taking and pullbacks."],
  [
    "bear",
    "Bear market",
    "Defensive traders, falling sentiment and bargain hunters.",
  ],
  [
    "mania",
    "Meme mania",
    "Faster trading, impulsive bets and sudden reversals.",
  ],
];
export function readWorld() {
  const stored = localStorage.getItem("norx.world");
  return worlds.some(([id]) => id === stored) ? stored : "balanced";
}
export function EconomyPicker({ world, onChange, busy }) {
  const dialog = useRef();
  return (
    <>
      <button
        className="economy-launch"
        disabled={busy}
        onClick={() => dialog.current.showModal()}
      >
        Economy: {worlds.find(([id]) => id === world)[1]} <span>⌄</span>
      </button>
      <dialog
        ref={dialog}
        className="economy-dialog"
        aria-label="Choose economy"
      >
        <header>
          <div>
            <small>CHOOSE YOUR WORLD</small>
            <h2>What kind of market?</h2>
          </div>
          <button
            aria-label="Close economies"
            onClick={() => dialog.current.close()}
          >
            ×
          </button>
        </header>
        <p>
          Each economy is a separate saved world with its own portfolio and
          $10,000 starting balance. Markets are shared with other players in
          that world.
        </p>
        <div className="economy-options">
          {worlds.map(([id, title, description]) => (
            <button
              key={id}
              aria-pressed={world === id}
              onClick={() => {
                dialog.current.close();
                if (id !== world) onChange(id);
              }}
            >
              <strong>
                {title} {world === id ? "✓" : "→"}
              </strong>
              <span>{description}</span>
            </button>
          ))}
        </div>
        <p className="muted">
          All funds are fictional. Scenarios influence behavior; gains are never
          guaranteed.
        </p>
      </dialog>
    </>
  );
}
