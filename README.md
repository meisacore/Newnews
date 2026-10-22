# NORX

A fictional USD trading world with Privy authentication, persistent portfolios,
30 inexpensive rule-based agents, shared AMM liquidity, and trade-derived candles.
No blockchain, wallets, deposits, withdrawals, LLMs, or external price feed.

## Development

Requires Python 3.10+ and Node 22+ (the current Privy SDK may require a recent Node).
Use this existing checkout; a separate Git worktree is unnecessary.

```sh
cd /workspace/Newnews
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend
npm ci --cache /tmp/norx-npm-cache
npm run build
```

Run these in separate terminals from the repository root:

```sh
.venv/bin/python worker.py
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
```

The API serves the built frontend at its root. For frontend development instead,
run `npm run dev` inside `frontend`; Vite proxies `/api` to port 8000.
The worker must run separately: API instances never start extra agent loops.
A local file lock prevents two workers using the same SQLite database.

### Privy setup

1. Create/select a Privy app and enable the desired email/Google login methods.
2. Configure your development and deployment origins in the Privy dashboard.
3. Set `PRIVY_APP_ID` on the backend and `VITE_PRIVY_APP_ID` in
   `frontend/.env.local` (see the example files). They must identify the same app.
4. Set `PRIVY_VERIFICATION_KEY` to the app's ES256 verification **public key** in
   PEM format. Literal `\n` sequences in that environment variable are supported.
   No app secret is required by this implementation.
5. Rebuild the frontend after changing its app ID and restart the backend after
   changing server environment variables.

The backend verifies the signature, ES256 algorithm, issuer `privy.io`, app audience,
expiration, issued-at claim, and Privy subject before trusting an identity.
Public browsing works without configuration; authenticated trading is disabled
until configuration is supplied. Live Privy sign-in requires your own app settings
and has not been tested using a real Privy account in this environment.

For a **local smoke test only**, start the backend with `NORX_DEV_AUTH=1` and leave
the frontend app ID unset. The UI offers an explicitly labeled shared local test
account. Never enable this bypass on a public deployment. Local development binds
to loopback by default.

### Storage and deployment scope

This version uses **SQLite**, not PostgreSQL. It is a runnable single-host MVP.
`NORX_DB` defaults to `data/norx.sqlite3`; preserve that directory on persistent
storage. Restarting processes preserves balances, agent state, trades, and pools.
No automatic market reset or hidden cash refill occurs. Starting USD is granted
exactly once per verified Privy user ID. Different Privy identities represent
separate game accounts; Sybil resistance is not included.

Before a public multi-host launch, migrate the ledger to managed PostgreSQL,
configure backups, HTTPS, request throttling, and worker supervision. Do not place
SQLite on a shared network filesystem. Trading history is currently retained in
full; plan retention/aggregation as usage grows. SQLite backups must include a
consistent database snapshot (use SQLite's backup API, not a live file copy).

## Market rules

- Three initial coins: FROG, RCKT, PBL. Each has fixed supply of 1,000,000 tokens.
- 100,000 circulating tokens per coin initially seed the pool. The remaining
  900,000 stay locked in treasury; they cannot be sold via the public API.
- Pool seed USD is explicit fictional genesis liquidity, separate from player
  and agent grants. Buy/sell fees are 0.3%, retained in pool liquidity.
- Trades use integer millionths of USD and whole token quantities. USD buys fill
  the largest whole quantity within the selected budget; unused USD stays in the
  account. Large buys and sells have real simulated price impact.
- Quotes expire after 30 seconds. Buy confirmations cannot exceed the quoted
  dollar cost. Sells have a fixed 1% minimum-proceeds tolerance. A quote can execute
  only once; retries return its original result. Mutations are transactional.
- The spot price is pool USD / pool tokens. Candles use fee-exclusive average
  execution prices; candles therefore need not equal spot prices. Volume is gross
  USD traded. Empty intervals carry the previous close and zero volume; no candles
  are fabricated before the first trade.
- Circulating market cap = spot price × circulating supply. FDV uses total supply.
  Neither implies that amount of USD was invested or can be withdrawn.
- Value, momentum, and noise agents have varied starting wealth, exposure limits,
  and activation probabilities. Wealth is independent of strategy. Shared calm,
  optimistic, or stressed conditions change perceived values, never prices directly.
- The simulation advances every two seconds while the worker is running. It
  continues when users sign out; downtime is paused rather than fast-forwarded.
- There are no promised profits. This is not calibrated to a real exchange.

## Validation

```sh
.venv/bin/python -m unittest -v
cd frontend
npm run build
```

Tests cover account separation, signed-token rejection, one-time grants under
concurrency, dollar budgets, quote ownership/expiry/slippage, replay protection,
restart persistence, candle gaps, market-cap calculations, and conservation across
300 simulation ticks. The browser smoke test is in `scripts/smoke_browser.py` (requires Playwright and Chromium; run against the local test mode with the Vite server running). The uploaded engine and its original tests are preserved as
`market.py`, `agents.py`, `test_market.py`, and `test_agents.py` for reference; the new
application runs `economy.py`. The old launch/graduation engine is not wired into
this MVP.
