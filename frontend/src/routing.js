const views = new Set(["pulse", "discover", "trade", "portfolio", "agents"]);
export function readRoute(location = window.location) {
  const legacy = location.hash?.slice(1) || "";
  if (legacy.startsWith("coin/")) {
    try {
      return { view: "coin", coin: decodeURIComponent(legacy.slice(5)) };
    } catch {
      return { view: "trade" };
    }
  }
  if (views.has(legacy)) return { view: legacy };
  const path = location.pathname.replace(/\/$/, "");
  const token = path.match(/^\/trade\/([^/]+)$/);
  if (token) {
    try {
      return { view: "coin", coin: decodeURIComponent(token[1]) };
    } catch {
      return { view: "trade" };
    }
  }
  return { view: views.has(path.slice(1)) ? path.slice(1) : "pulse" };
}
export function routePath(route) {
  return route.view === "coin"
    ? "/trade/" + encodeURIComponent(route.coin)
    : "/" + (views.has(route.view) ? route.view : "pulse");
}
export function isMarketPath(path) {
  return /^\/(?:pulse|discover|trade(?:\/[^/]+)?|portfolio|agents)\/?$/.test(
    path,
  );
}
export function canonicalizeLegacy() {
  const legacy = window.location.hash.slice(1);
  const knownHash = views.has(legacy) || legacy.startsWith("coin/");
  if (
    ["/market.html", "/market"].includes(window.location.pathname) ||
    knownHash
  ) {
    history.replaceState(
      history.state,
      "",
      routePath(readRoute()) +
        window.location.search +
        (knownHash ? "" : window.location.hash),
    );
  }
}
export function navigate(path) {
  if (window.location.pathname === path && !window.location.hash) return;
  history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
export function startNavigation() {
  const click = (event) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    const link = event.target.closest?.("a[href]");
    if (
      !link ||
      link.hasAttribute("download") ||
      (link.target && link.target !== "_self")
    )
      return;
    const url = new URL(link.href, window.location.href);
    if (
      url.origin !== location.origin ||
      url.search ||
      url.hash ||
      !isMarketPath(url.pathname)
    )
      return;
    event.preventDefault();
    navigate(url.pathname);
  };
  document.addEventListener("click", click);
  return () => document.removeEventListener("click", click);
}
