# NORX

A fictional USD trading world with Privy authentication, persistent portfolios,
36 rule-based agents with different wealth and judgment, shared AMM liquidity, trade-derived candles, the original animated starry welcome page, and a live three-column Pulse feed.
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

Start the backend from the repository root:

```sh
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
```

The backend **starts the simulation automatically**. A separate worker terminal is
no longer required. For Windows local test mode use PowerShell:

```powershell
$env:NORX_DEV_AUTH="1"
.\.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Then run `npm run dev` in `frontend` in a second terminal. Keep the frontend app ID
unset to use the local test account.

The API serves the starry welcome page at `/` and the trading application at `/market.html#pulse`. ENTER WORLD transitions between them. Both pages are built by Vite; the welcome page loads without React or Privy. For frontend development instead,
run `npm run dev` inside `frontend`; Vite proxies `/api` to port 8000.
A cross-platform file lock allows only one simulation owner per database, including
when several API processes or a standalone worker are running. A waiting API takes
over if the owner exits. To run a dedicated worker instead, set `NORX_AUTO_WORKER=0`
on the API and run `.venv/bin/python worker.py` separately. Relative `NORX_DB` paths
resolve from the project root for both processes, regardless of terminal directory.

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
No automatic market reset or hidden cash refill occurs. API responses include a successful-tick heartbeat; Pulse distinguishes a running simulation, a paused simulation, and a missing/outdated backend. Starting USD is granted
exactly once per verified Privy user ID. Different Privy identities represent
separate game accounts; Sybil resistance is not included.

Before a public multi-host launch, migrate the ledger to managed PostgreSQL,
configure backups, HTTPS, request throttling, and worker supervision. Do not place
SQLite on a shared network filesystem. Trading history is currently retained in
full; plan retention/aggregation as usage grows. SQLite backups must include a
consistent database snapshot (use SQLite's backup API, not a live file copy).

## Market rules

- Three initial coins: FROG, RCKT, PBL. Each has fixed supply of 1,000,000 tokens.
- The worker launches **five random coins every 60 seconds**, starting one minute
  after initialization/upgrade. Names, unique symbols, initial pool USD ($1,500–$12,000),
  and circulating pool tokens (50,000–200,000) vary. Every coin has independent
  liquidity, a persisted launch timestamp, and its own trade-derived chart.
- Each new pool's fictional USD seed is recorded in the `launches` ledger. This is
  explicit game-world issuance, not USD taken from or given to existing users.
- The launch schedule survives restarts. After downtime one due batch is launched,
  followed by the next batch 60 seconds later; missed minutes are not backfilled.
- Pulse has **New pairs**, **Final stretch**, and **Migrated** columns. Activity
  progress is cumulative traded USD / starting pool USD: under 70%, 70–100%, and
  100% respectively. Migrated is an established activity stage, not a blockchain
  or liquidity migration; every stage trades through the same AMM.
- Pulse shows up to the newest 60 coins per column, with real counts, market cap,
  volume, transaction count, holders, search, sorting, and USD buy-ticket shortcuts.
  An older coin remains tradable by its `market.html#coin/<id>` URL and from its
  saved portfolio position. Nothing is deleted when it leaves the feed.
- Agent work is bounded: each tick samples up to eight of the 40 newest markets
  plus up to four markets with agent holdings. Agents retain finite budgets; newly
  launched markets compete for attention and liquidity rather than forcing trades.
- 100,000 circulating tokens per coin initially seed the pool. The remaining
  900,000 stay locked in treasury; they cannot be sold via the public API. Random
  launches vary their circulating allocation; their remaining supply is also locked.
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
restart persistence, candle gaps, market-cap calculations, conservation across
300 simulation ticks, timed launch boundaries, duplicate prevention, migration of
existing databases, lifecycle stages, and trading newly launched coins. The browser smoke test is in `scripts/smoke_browser.py` (requires Playwright and Chromium; run against local test mode with Vite and the backend running). It checks the original welcome transition, Pulse, USD buy/sell, reload recovery, mobile layout, and an actual timed five-coin launch. It takes about a minute. Set `BROWSER_EXECUTABLE` for a system Chromium binary, or install Playwright Chromium with `python -m playwright install chromium`. The uploaded engine and its original tests are preserved as
`market.py`, `agents.py`, `test_market.py`, and `test_agents.py` for reference; the new
application runs `economy.py`. The old launch/graduation engine is not wired into
this MVP.

## Updating an existing local installation

Stop the frontend, backend, and worker before updating source files. Preserve
`data/`, any `.env` files, and `frontend/.env.local`; do not replace them with
files from a fresh download. Install requirements, run `npm ci` in `frontend`,
and restart the backend and frontend. The backend starts the simulation automatically; close any old standalone worker so outdated code does not retain the simulation lock. Database migrations are additive and preserve
accounts, holdings, pools, and trade history. The first new launch arrives about
one minute after the updated worker starts (or immediately if a saved batch is due).

The sky photo in `frontend/public/sky-bg.jpg` is the optimized image supplied with
the uploaded NORX design. Its welcome-page star animation and entry transition
are preserved. Privy loads only when an app ID is configured; local test mode
does not load the Privy SDK.

### If Pulse shows zero coins or no launches

Stop all old backend and worker terminals before updating. Update the entire source
folder, not just the frontend; keep `data/` and local environment files. Start the
updated backend and Vite. The API should immediately return the three starter coins
(or the existing saved world), and the first scheduled five-coin batch follows
within a minute. The frontend rejects an outdated API response with a clear restart
message instead of silently interpreting missing stage metadata as zero coins.
`GET /api/state` reports `api_version: 3`, `simulation.running`, `last_tick_at`,
`total_coins`, and `next_launch_at`. No database deletion is needed.

## Agent personalities and wealthy traders

The original shared 3%-of-cash order rule and $15,000 maximum initial agent
balance have been replaced by personality-specific sizing and execution checks.
The existing 30 traders retain their current balances and holdings and receive
patient-value, contrarian, disciplined-trend, FOMO, gambler, or small-retail
personalities. Six additional agents receive these one-time virtual USD grants:

| Agent | Personality | Initial virtual USD |
|---|---|---:|
| Atlas | Patient value investor | $500,000 |
| Sage | Cautious contrarian | $350,000 |
| Comet | Reckless whale | $1,500,000 |
| Lucky | Impulsive gambler | $750,000 |
| Echo | FOMO chaser | $250,000 |
| Vector | Disciplined trend trader | $400,000 |

The $3.75 million in new fictional capital is recorded in `agent_grants`, once
per new agent. Restarting or losing money does not refill these accounts. Human
accounts and original agent balances are not changed by the migration.

Disciplined agents check their noisy perceived value against **actual average
execution cost including fees**, and size down to respect low price-impact
limits. They can hold instead of buying an overpriced asset. Reckless whales
ignore perceived value, may commit 8–30% of available cash to an order within
their exposure and execution limits, and may dump positions without protecting
profit. Gamblers and FOMO agents make different speculative decisions; panic
selling and overpayment can produce real losses within the fictional ledger.
Even reckless agents retain hard solvency and liquidity limits. A single order
can tolerate up to 250% average execution premium, so it can move a thin market
sharply; no agent may spend money it does not have or empty a pool. Global
cooldowns prevent one bot trading every sampled coin in the same tick.

The **Agents** tab shows personalities, available cash, one-time grants, trade
counts, exposure limits, and each agent's biggest buy. **Whale watch** on Pulse
retains the ten latest trades of $1,000 or more; opening an item shows its coin's
chart. Trade activity includes agent names and the rule behind their decision.
Wealth does not imply good judgment, and disciplined rules do not guarantee a
profitable outcome. All order sizes, quotes, prices, and cash flows are real
within the simulation, not decorative large-order messages.

The personality browser check is `scripts/smoke_agents.py`: it verifies the
36-agent dashboard, one-time grant labels, naturally occurring large trades,
Whale watch navigation into the chart, and mobile layout. It does not inject
fake trades. Set `NORX_TEST_URL` and `BROWSER_EXECUTABLE` as needed.
