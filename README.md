# NORX

A fictional USD trading world with Privy authentication, persistent portfolios,
2,000 rule-based agents per world with different wealth and judgment, shared AMM liquidity, trade-derived candles, the original animated starry welcome page, and a live three-column Pulse feed.
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

- Three initial coins: FROG, RCKT, PBL. Each has fixed total supply of 1,000,000,000 tokens.
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
counts, exposure limits, and each agent's biggest buy. **Whale watch** in the activity panel
retains the ten latest trades of $1,000 or more; opening an item shows its coin's
chart. Trade activity includes agent names and the rule behind their decision.
Wealth does not imply good judgment, and disciplined rules do not guarantee a
profitable outcome. All order sizes, quotes, prices, and cash flows are real
within the simulation, not decorative large-order messages.

The personality browser check is `scripts/smoke_agents.py`: it verifies the
36-agent dashboard, one-time grant labels, naturally occurring large trades,
Whale watch navigation into the chart, and mobile layout. It does not inject
fake trades. Set `NORX_TEST_URL` and `BROWSER_EXECUTABLE` as needed.

## Pulse controls and simulation status

The uploaded reference docs inform the Pulse interactions; NORX keeps its starry
navy/gold design, virtual USD, fictional launches, AMM, and agent personalities.
Each column now has P1/P2/P3 buy-ticket presets ($25/$50/$250), independent sorting
and filters for USD market cap, USD volume, holders, and token age. Preferences
stay in the browser. A preset prepares the existing trade ticket and its quote;
it does not bypass confirmation or execution limits. Missing figures fail an
active numeric filter rather than being treated as zero.

Hovering a column or scrolling its list temporarily holds its cards and displayed
figures. The hold control can pin that view; Resume releases waiting arrivals.
This affects the display only: the simulation, Whale watch, and execution quotes
continue updating. The reserved arrivals strip prevents hover from shifting a
card under the pointer. Filters float over the column to keep its layout aligned.
All scrollbars use dark navy tracks and muted gold thumbs; Whale watch also has
keyboard-accessible left/right controls.

Simulation status is based on the **completion** of a successful tick and sampled
after the database heartbeat is read. This fixes a boundary race where a new tick
looked newer than the API request's captured clock and was incorrectly shown as
paused. Heartbeats up to 10 seconds old are Live, 11–30 seconds are Updating,
and over 30 seconds (or no completed tick) are Paused. A failed transaction does
not refresh the heartbeat. API polling is sequential and cancels obsolete
requests so slow responses cannot overwrite newer market state.

Run the additional frontend checks with:

```sh
node --test frontend/src/marketState.test.js frontend/src/pulseLogic.test.js
```

`scripts/smoke_pulse_controls.py` uses a controlled UI stream to test slow-response
polling, held arrivals, independent filters, preset persistence, delayed versus
paused states, themed scrollbars and mobile layout. It does not submit trades or
modify the economy. Its screenshots reload the actual market stream separately.

### Compact trading workspace

The trading app uses a full-width terminal layout inspired by the supplied Trial
capture, with NORX branding, the original star field, and the welcome animation.
A shared status strip shows market count, agent population, economy, and available
virtual USD. Discover is a searchable table with volume, gainers, market-cap and
newest sorting, plus launch-stage filters. Its $50 buttons prepare the trade ticket.

Coin pages keep the real candlestick chart and add pool/holder/stage statistics,
$25/$50/$250/$1,000 buy presets, and sell presets based on the player's holdings.
Every order still requires preview and confirmation. The execution table filters
by market versus personal trades and by buy/sell side. The state endpoint includes
up to 50 recent `coin_trades` for the selected market, separately from the world
feed, using the same public identity redaction. This prevents an active world
from hiding a quieter coin's executions. This is market-order simulation; the
interface does not offer unsupported limit orders or invented performance data.

After building, run against an API with `NORX_DEV_AUTH=1`:

```sh
NORX_TEST_URL=http://127.0.0.1:8000 BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python scripts/smoke_terminal.py
```

It submits a virtual buy to
the test account, checks search/sorting/execution filters, and checks five mobile
routes. Use a separate temporary `NORX_DB` for this test.

### Reference interface redesign

The uploaded `trial-main.zip` is a visual reference. NORX uses the reference's layout with its own navy surfaces,
gold accents, slim header, separate full-height Pulse columns, presets
in column headers, fixed status bar, and floating mobile navigation. NORX's star
field and animated welcome remain; the welcome typography and button match the
exchange. The reference's disconnected pages and placeholder controls are not
used as NORX market data.

Global market search opens with the header button or `/` (also Ctrl/Cmd+K outside
text fields), searches names, symbols and coin IDs, and opens real market charts.
Escape closes the native modal. The header equity estimate is cash plus holdings
at spot prices. Portfolio shows that breakdown, saved positions, and the latest
50 account executions. Equity and position values are estimates, not guaranteed
sale proceeds. The trade workspace combines the chart and coin execution feed
with a USD order ticket and a live position summary. Privy configuration and all
existing virtual-money/agent rules remain unchanged.

The terminal browser check also exercises global search, saved portfolio rows,
three desktop columns, and five routes at mobile width. The Pulse control check
checks the themed navy tracks and muted gold scrollbars on Discover.

[View the updated Pulse interface](docs/interface-preview.png) (captured from the
running NORX simulation, with real simulated coins and agent activity).

### Blank screen after Enter World

The exchange HTML contains its own dark, starry loading screen before JavaScript
starts. A failed app-module load displays an error and reload link; a React startup
error is caught by the app boundary. Slow startup displays guidance after 15 seconds.
The welcome and exchange no longer wait for external Google Fonts.

Vite selects the authentication entry from `VITE_PRIVY_APP_ID`: without an ID,
local mode does not scan or bundle the Privy SDK. With an ID, the lazy Privy entry
is used. Restart Vite after changing that setting or updating the project.
If an older development dependency cache is still present, stop the frontend and
run this in `frontend` (also works in PowerShell):

```sh
npm run dev -- --force
```

Then hard-refresh the browser with Ctrl+Shift+R. Run
`NORX_TEST_URL=http://127.0.0.1:5173 .venv/bin/python scripts/smoke_startup.py`
from the repository root to check the Vite startup path and module-load failure UI.

### Trade picker, hot buys, and a larger crowd

Trade opens `#trade`, a searchable market picker, instead of linking to a default
FROG chart. Selecting any market opens that market's chart and USD ticket.
Discover contains a ranked screener, with Trending, Top, Gainers, and New pairs views. Whale watch opens in a separate activity panel. Discover and the picker have period controls and
sorts for heat or recent buy USD. The API aggregates actual five-minute buy/sell
USD, buy/sell counts, and distinct buyers across every coin, including older coins
outside the latest launch feed. Heat is buy USD × log2(2 + distinct buyers) × the
buy share of trade count. It is current activity, not a prediction. Sell-only or
expired activity does not qualify. Dollar figures include the actual trade fees.

The world now maintains at least 2,000 persistent trader accounts. Upgrading a
36-agent world adds 1,964 entrants with varied personas and finite initial funds;
existing accounts, holdings, pools, and balances stay intact. Most entrants have
small budgets, with fewer moderate and wealthy entrants. Each new identity gets
one recorded starting grant; restarts never refill it. These grants expand the
fictional money supply once, on upgrade, rather than continuously creating money.

The worker randomly samples up to 256 eligible traders per two-second tick, with
personality-specific activation and cooldowns, and considers each sampled trader
at most once per tick. Traders can revisit their existing positions and sell.
The population is real accounts with independent holdings, not a counter or
2,000 simultaneous orders. The Agents page searches the full population and
renders 40 traders per page. In a temporary local benchmark, initializing 2,000
accounts took about 25 ms, and 30 early ticks averaged about 6 ms each; larger
histories and other machines will vary.

`test_crowd.py` checks upgrade preservation, one-time funding, bounded cohorts,
participation, rolling heat, distinct buyer counts, and older hot markets.
`scripts/smoke_heat.py` checks the picker, chosen coin chart, actual trending data,
pagination, search, the star background, and mobile layouts against a running
backend. Restart both backend and frontend after updating to activate the crowd.

### NORX branding and focused Pulse

Pulse contains the three launch-stage feeds, search, presets, and launch countdown.
Trending is represented by the screener ranking on Discover. Whale watch opens
in its own activity drawer from the header or screener controls. NORX is uppercase with a gold X throughout the
header, welcome, and startup screen. The original DM Sans body and Manrope
interface headings are restored, with Cormorant Garamond on the welcome page.
Navy surfaces, gold accents, and stars are retained; buys/gains remain green and
sells/losses red. Fonts are self-hosted under `frontend/public/fonts` with their
SIL Open Font License files and `font-display: swap`, so no Google Fonts request
blocks startup.

### Discover screener and USD / ETH

Discover uses ranked, compact rows with sortable market cap, price, age,
transactions, volume, traders, period changes, and buy/sell flow. Trending is a
table view, not an extra ticker above the table. The 5m/1h/6h/24h buttons select
the actual trade window used for ranking, volume, transaction and trader counts.
Price changes compare the current pool spot with the last execution at/before
the window start, falling back to the first known execution for younger coins;
unknown history shows a dash. The totals cover all markets; the table covers
the current feed plus leading active markets from each window. Market data
uses API version 5 so an older backend reports that it needs restarting rather
than silently omitting the screener statistics.

Whale watch is a separate panel opened from the wave icon in the header or the
screener's Whale watch button. It shows each trade's market, time, size, and
personality and opens that market's chart. It occupies no space above Discover
or Pulse.

The saved USD/ETH selector changes monetary displays, chart prices/volume,
portfolio valuations, filters, and buy inputs. ETH is a **simulated quote unit**
at a fixed paper rate of **1 ETH = $3,000**; it is not live Ethereum pricing, a
wallet, or a blockchain transaction. The ledger, liquidity pools, grants, and
fees remain in integer micro-USD. A 0.1 ETH buy creates a $300 USD budget before
preview/confirmation. Token sell quantities remain whole tokens; their proceeds
are displayed in the selected unit. Changing units never grants funds or edits
balances. Existing preset budgets keep their USD value and display the ETH
equivalent. New ETH ticket presets are 0.01/0.05/0.1/1 ETH.

`test_screener.py` checks period boundaries, distinct traders, true volume and
price baselines. `money.test.js` checks conversion and formatting.
`scripts/smoke_screener.py` checks sorting/windows, the separate activity panel,
persistence, an actual 0.1 ETH virtual buy and token sale, and five mobile routes.
Restart both servers after updating; preserve the existing data directory.

[View the Discover screener](docs/discover-preview.png).

### Unified token terminal and one-billion supply

The token page uses a compact identity/liquidity/period header over the chart
and scrolling trade tape, with a separate trade ticket and token-info column.
Candle sizes are 1m/5m/15m/1h. The independent 24h view requests a full day of
available candles, rather than just changing a label; it defaults to 5m candles
and supports finer/coarser choices. New markets show only real available trades.
Positions shows the signed-in player's actual balance and spot value.

Every live-engine token has a total supply of **1 billion**. On upgrade, each
legacy one-million token undergoes a 1,000-for-1 denomination change: pool and
holding quantities and historical trade quantities multiply by 1,000; spot,
reference and historical execution prices divide by 1,000. USD account and pool
balances, fees, trade amounts, ownership shares, market caps, and historical
volume stay unchanged. Cached completed-quote results scale their quantities
for idempotent replays; unexecuted quotes expire and must be previewed again.
The transaction validates actual per-coin supply, rolls back unsupported totals,
and does not rescale an already upgraded coin. New coins allocate 50–200 million
tokens to their initial pool; the remaining supply stays in treasury.

**Stop the existing backend and any standalone worker before updating/restarting.**
Keep the existing data directory. The backend upgrades the database automatically.
API version 5 detects an older backend instead of displaying stale supply data.
`test_supply.py` verifies supply, value/history conservation, replay handling and
rollback. The API tests verify actual day-long candle coverage.
`scripts/smoke_token.py` checks the token terminal, 24h/15m controls, supply info,
USD/ETH input round trips, a real virtual buy, positions and mobile layout.

[View the token terminal](docs/token-preview.png).

## Economy scenarios and trade tray

Use **Economy** in the bottom status bar to choose Balanced, Bull run, Bear market,
or Meme mania. The choice is saved in this browser. Each world has separate coins,
agent balances, player portfolios, trade history and quotes; switching worlds does
not reset a previous world or change other players' scenario. Players choosing the
same world share that market. Each account gets its one-time fictional $10,000
starting grant separately in each world. Scenarios change risk appetite, activity
and reference-value drift, rather than prescribing prices or guaranteeing returns.

The existing `NORX_DB` remains the Balanced world. Other worlds are created lazily
alongside it with `-bull`, `-bear`, or `-mania` before the database extension. The API
auto-starts one locked worker for each opened world, and shuts them down on exit.
Keep **all** these database files when updating. With `NORX_AUTO_WORKER=0`, run a
separate worker against each desired world database using `NORX_DB`.

Agents review their own holdings directly, including coins outside the launch
feed. They can take profits, cut losses and rotate older positions. Buy orders are
limited to 6% of the quote-side pool reserve (15% for reckless whales), in addition
to each trader's finite cash and execution-cost limits. Large orders remain possible
in deeper pools. These rules do not rewrite past prices, balances or trades.
Market cap is spot price times circulating supply, not dollars invested. Discover
now shows the quote-side pool reserve under market cap; trades, volume and trader
counts use the chosen time window and are never inflated to match market cap.

On a token page, choose **Expand trades** to give the execution tape more space,
or drag the gold divider between the chart and tape. The divider supports keyboard
Up/Down and Home/End keys. **Restore chart** returns the chart; drag sizing is saved
in this browser. Stars, original fonts and the gold theme remain in place.
