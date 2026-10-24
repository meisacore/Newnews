# NORX on Cloudflare Workers with Static Assets

This runs the website and `/api` on the same Cloudflare URL. Supabase remains the
source of truth for accounts, virtual USD, holdings, coins, quotes and executions.
Privy is email-only; NORX does not create wallets. No Python server is needed after
cutover. This is a **Workers** deployment, not a Pages deployment.

The existing Python/SQLite development path still works. You do not need to repeat
the SQLite-to-Supabase migration. Cloudflare preparation adds functions and one small
runtime table to each private world schema; it retains the existing ledger. Missing
Bear/Mania worlds are initialized with the normal one-time agent grants.

## 1. Update and install

Download/update the complete repository from GitHub. Keep your `data/`, `.env`,
`frontend/.env.local` and virtual environment. Node 22 or newer is required.

In PowerShell, from `C:\Users\user\Newnews-main`:

```powershell
npm ci --prefix frontend
npm ci --prefix cloudflare
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Stop the old Python API and all `worker.py` processes with Ctrl+C before cutover.
Keep your existing Supabase backup/SQLite copies.

## 2. Prepare the existing database

In the terminal where your working `DATABASE_URL` is set:

```powershell
.\.venv\Scripts\python cloudflare\prepare.py --activate
```

If this is a new terminal, set `DATABASE_URL` privately to your working Supabase
**session pooler, port 5432** connection string first, with `?sslmode=require`.
Use the percent-encoded database password you already configured. Never put this
URL in a `VITE_` variable, frontend file, GitHub commit or chat message.

The command refuses cutover while a Python simulation owns any world. It prints
`Engine: cloudflare` when finished. Preparation is repeatable; rerunning it does
not reissue grants, reimport SQLite or delete trades. Activation clears only
cached public snapshots and scheduling timestamps.

For a preparation-only check without switching engines, omit `--activate`.
The updated Python engine remains idle if accidentally started after activation.
Do not run an old, unupdated Python checkout against these same worlds.

## 3. Cloudflare login and database secret

```powershell
cd cloudflare
npx wrangler login
npx wrangler secret put DATABASE_URL
```

At Wrangler's secret prompt, paste the **complete working PostgreSQL URL** privately,
then press Enter. This secret belongs to the Worker, not to Privy. Wrangler may
ask to create the Worker on its first secret operation; use the `norx` name from
`wrangler.jsonc`. Set `NORX_PG_SCHEMA_PREFIX` in that file only if your existing
installation uses a nondefault prefix.

The default configuration uses direct PostgreSQL connections to the session
pooler. Optional later optimization: bind a Cloudflare Hyperdrive configuration
as `HYPERDRIVE` and **disable its query caching** (`max_age=0`). The code prefers
that binding over `DATABASE_URL`. Database-level quote/trade atomicity must never
rely on cached queries. Hyperdrive is optional; check its own limits before adding
it. No Supabase service-role API key is required for this connection path.

## 4. Build and publish

From the `cloudflare` folder:

```powershell
npm run deploy
```

This builds the existing star-themed frontend and publishes it with the Worker.
Use the `https://norx.<your-account>.workers.dev` address printed by Wrangler.
Add that exact origin to the allowed origins for Privy app
`cmvjqf2i1030e0hl9wck83jj1`. Add your custom domain there too when you connect one.
Keep Email enabled in the Privy dashboard. The frontend now requests only Email;
Google is no longer offered by NORX. Existing Privy accounts are not deleted.

Open `/api/config` on the deployed URL: `dev_auth` must be false and
`privy_configured` true. Open the welcome page, Enter World, log in by email and
check your portfolio in the correct economy. Watch for five launches after a
minute in an active world. A shared world uses your original saved Supabase data,
not a fresh browser-only balance. New Privy identities get the usual $10,000 once
per world. Changing login methods does not manually merge different Privy user IDs.

Cron triggers can take several minutes to propagate after deployment. Visible
visits also advance due batches, so startup does not depend on Cron propagation.
Use `npx wrangler tail` for live errors; logs deliberately omit tokens, database
URLs and private account records. The API never enables the local-demo login.

If a website already exists on Pages, leave it alone until this Worker URL works.
Then point your domain at the Worker through Workers & Pages → NORX → Settings →
Domains & Routes. The frontend's relative `/api` requests need no separate API host
or CORS configuration. Avoid serving this new frontend from the old Pages host
unless you explicitly configure a proxy to this Worker.

## How the simulation runs

* At most one short, database-atomic cohort runs per **10 seconds per active world**,
  shared across all visitors. It evaluates up to 256 of the 2,000 rule-based agents;
  activation probabilities and cooldowns determine who trades. The scheduler runs
  once per minute and visits worlds sequentially. There is no always-running loop.
* Worlds remain active for roughly two minutes after their last uncached visible
  visit. They then pause. On return, their saved ledger resumes and the next launch
  is scheduled a minute later. Downtime does not generate a backlog of launches.
* Each active world launches five random one-billion-supply coins per minute. Cash
  and token movements, fees, price limits and idempotent receipts stay in PostgreSQL
  transactions with the same world lock used by the previous engine. Existing
  Python receipts can be retried safely through the new API.
* Public snapshots are generated once per batch inside PostgreSQL and saved in Supabase. The Worker passes through the resulting JSON text rather than loading and transforming thousands of rows. Trader profiles are returned only on the Agents tab; other tabs receive the total agent count. A five-second
  Cloudflare public cache and the existing browser cache share reads. Selected-token
  history and candles remain real trade data. Cached public prices can lag a batch;
  private execution always checks the current pool. Portfolios/quotes/trades are
  never edge-cached. Successful execution returns its receipt immediately.
* Browser market polling remains 10 seconds, portfolio polling 60 seconds plus
  login/trades/returning to the tab. Hidden tabs stop recurring polling. Edge hits
  reduce database work; they still count as incoming API requests to Cloudflare.

This reduces idle work and removes a separate Python hosting bill. **It does not
promise unlimited free operation.** Workers requests/CPU, Supabase storage and
compute, and Privy all have limits. Agent trades and five launches per minute
still grow the database while a world is active. This release does not delete old
user history or silently prune coins. Monitor usage before inviting many players;
choose retention limits deliberately when growth needs them. Stay on the free plan
if you do not want paid usage, and watch its dashboard limits rather than enabling
a paid plan or assuming an exhausted free quota will keep serving traffic.

## Local Workers test

Keep a separate test database, or stop the Python simulation first. From
`cloudflare`, create the ignored `.dev.vars` file locally:

```dotenv
DATABASE_URL="YOUR_COMPLETE_DATABASE_URL_WITH_SSLMODE_REQUIRE"
```

Never commit that file. Build the frontend from the repository root, then start:

```powershell
npm run build --prefix frontend
cd cloudflare
npm run dev
```

Open `http://localhost:8787` and add that origin to Privy allowed origins for email
login. This uses the real database named in `.dev.vars`; use a disposable project
for experiments. Local Cron is not automatic; trigger it by opening
`http://localhost:8787/cdn-cgi/handler/scheduled` while the local Worker is running.
Do not use `--remote` for local experiments against production secrets.

## Verification and rollback

The repository includes real PostgreSQL checks for exact integer AMM parity with
Python, conserved USD and token supply, simultaneous trade retries, private-data
redaction, email-session JWT validation, world isolation, launches and idle resume.
With a **disposable** PostgreSQL database, from the repository root:

```powershell
$env:NORX_TEST_POSTGRES_URL="YOUR_DISPOSABLE_TEST_DATABASE_URL"
.\.venv\Scripts\python scripts\test_cloudflare.py
node --test frontend/src/*.test.js
```

The test harness creates unique `norx_cf_test_*` schemas and removes them afterward.
For a build-only verification without deployment: `npm run build --prefix cloudflare`.

To return to Python, first stop routing players to the Worker and disable its Cron
trigger. From the root, in the terminal with the working `DATABASE_URL`:

```powershell
.\.venv\Scripts\python cloudflare\prepare.py --deactivate
$env:NORX_DEV_AUTH="0"
.\.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

This returns the same Supabase ledger to the Python engine; it does not restore an
old SQLite copy or discard trades made since deployment. The Cloudflare engine
refuses new batches once the database mode is `python`.


## Updating after a Worker CPU limit error

If logs show `Exceeded CPU Limit`, install the updated SQL rendering functions and
Worker code. Merely increasing polling intervals does not remove snapshot-building
CPU from a request. The thin Worker path runs aggregation and JSON assembly in
PostgreSQL and passes through JSON text; all 2,000 trader profiles load only on the
Agents tab. This addresses the expensive path, but actual deployed usage must
still fit your plan's CPU and request limits.

Keep your local `cloudflare/wrangler.jsonc` when updating: it contains your live
Hyperdrive binding ID. Keep `.env`, `.dev.vars`, `frontend/.env.local`, and data too.
From the repository root, in the terminal with the working `DATABASE_URL`:

```powershell
.\.venv\Scripts\python cloudflare\prepare.py
if ($LASTEXITCODE -ne 0) { throw "Database setup failed; stop here." }
cd cloudflare
npm run deploy
```

Omit `--activate` for this update: these worlds already use Cloudflare, and cached
snapshots and engine settings can stay in place. This adds/replaces SQL functions,
not a repeat data import. After deployment, reload the site and inspect
`npx wrangler tail` for any new CPU failures. Hyperdrive query caching must remain
disabled; do not remove your existing binding when copying updates.
