import React, { useEffect, useRef } from "react";
import { X } from "lucide-react";
import WhaleWatch from "./WhaleWatch";
import { useCurrency } from "./Currency";
export default function ActivityDrawer({ open, onClose, state, busy, onOpen }) {
  const dialog = useRef(null);
  const money = useCurrency();
  useEffect(() => {
    if (open && !dialog.current.open) dialog.current.showModal();
    else if (!open && dialog.current.open) dialog.current.close();
  }, [open]);
  return (
    <dialog
      ref={dialog}
      className="activity-drawer"
      aria-label="Whale watch panel"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === dialog.current) onClose();
      }}
    >
      <div className="activity-drawer-content">
        <header>
          <div>
            <h2>Whale watch</h2>
            <p>Recent simulated trades above {money.format(1000)}</p>
          </div>
          <button aria-label="Close whale watch" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <WhaleWatch
          state={state}
          busy={busy}
          onOpen={(id) => {
            onOpen(id);
            onClose();
          }}
        />
        {!state?.large_trades?.length && (
          <p className="empty-market">
            Large trades will appear as the market trades.
          </p>
        )}
      </div>
    </dialog>
  );
}
