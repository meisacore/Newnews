// One in-flight refresh; hidden documents produce no recurring requests.
export function visiblePolling(
  task,
  interval,
  {
    document: doc = document,
    setTimer = setTimeout,
    clearTimer = clearTimeout,
  } = {},
) {
  let stopped = false,
    running = false,
    queued = false,
    timer;
  const clear = () => {
    clearTimer(timer);
    timer = undefined;
  };
  async function refresh() {
    clear();
    if (stopped || doc.hidden) return;
    if (running) {
      queued = true;
      return;
    }
    running = true;
    try {
      await task();
    } finally {
      running = false;
      if (!stopped && !doc.hidden) {
        if (queued) {
          queued = false;
          void refresh();
        } else timer = setTimer(() => void refresh(), interval);
      }
    }
  }
  function visibility() {
    if (doc.hidden) {
      clear();
      queued = false;
    } else void refresh();
  }
  doc.addEventListener("visibilitychange", visibility);
  void refresh();
  return {
    refresh,
    stop() {
      stopped = true;
      clear();
      doc.removeEventListener("visibilitychange", visibility);
    },
  };
}
