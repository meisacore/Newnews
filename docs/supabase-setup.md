# Connect NORX to Supabase

Privy continues to handle sign-in. Supabase is used only as PostgreSQL storage;
no Supabase Auth integration or browser database client is needed. The backend
stores the verified Privy subject, balances, holdings, quotes and executions.
It does not store users' login passwords or access tokens.

## 1. Get the backend connection URL

In your Supabase project, open **Connect**, select **Session pooler**, and copy
the PostgreSQL URI on port **5432**. Replace its password placeholder with your
database password. URI-encode special characters in the password. Use the database
password, not a Supabase anon/publishable/service-role API key.

Use session pooling because NORX holds a PostgreSQL session advisory lock for
simulation ownership. Transaction pooling on port 6543 is rejected. A direct
connection on 5432 also works if your computer/host supports the endpoint's network
and IP version. Remote connections require TLS; `sslmode=require` is added when
not supplied. `verify-full` is also supported with appropriate CA configuration.

Never paste the URI into chat, commit it, or put it in a `VITE_` variable. Keep it
in the backend terminal environment or your hosting provider's secret settings.
The root `.env.example` is documentation; the server does not auto-load `.env`.

## 2. Stop the simulation and back up existing data

Stop the backend with Ctrl+C, and stop any standalone workers. Make a copy of the
whole `data` folder, including any `-wal` files. Leave your original files in place.
Avoid using several checkouts against the same PostgreSQL database during import.

Update the project from GitHub, then in PowerShell at the repository root:

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Set `DATABASE_URL` privately. This prompt hides input and keeps the value out of
PowerShell command history (the placeholder itself is not a real URL):

```powershell
$norxConnection = Read-Host "Paste your Supabase Session pooler URI" -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new("", $norxConnection).Password
$env:NORX_DEV_AUTH = "0"
```

The environment variable lives in this terminal session. Set it again after opening
a new terminal. Do not print `$env:DATABASE_URL` or share terminal environment dumps.

## 3. Preview and import saved worlds

**Do this before starting the backend with DATABASE_URL set.** A new backend starts
a fresh market when it finds an empty world. The importer refuses to overwrite one.

```powershell
.\.venv\Scripts\python migrate_storage.py --source .\data\norx.sqlite3
```

This previews row counts from temporary snapshots and does not connect to or write
the destination database. It includes existing `-bull`, `-bear`, and `-mania`
sibling files. If your local `NORX_DB` was customized, use that path as `--source`.
Missing sibling worlds are skipped; no source files is an error.

Check that the expected worlds and counts appear, then run:

```powershell
.\.venv\Scripts\python migrate_storage.py --source .\data\norx.sqlite3 --apply
```

The importer copies accounts, holdings, pools, history, agents and completed quote
results. It uses SQLite's snapshot backup API, applies any legacy schema/supply
upgrade only to a temporary copy, verifies row counts, and leaves the originals
unchanged. Pending quotes expire so the user must preview again. Trade IDs and
completed retry results are preserved. Each world's import commits atomically;
a failure rolls that world back. Several worlds are separate transactions.
If some worlds were already imported, retry only a remaining world with
`--world bull`, `--world bear`, etc. A populated destination is always refused.
Never delete a populated schema just to bypass this check.

If you have no saved portfolios to keep, skip the importer; the backend can create
fresh markets directly. Existing local demo holdings remain owned by the local
demo identity, not assigned to a Privy user.

## 4. Start and verify

In the same terminal:

```powershell
.\.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Start/restart the frontend as usual. Sign in using the same Privy account, select
the same economy, and verify the saved balance and holdings. Make a small fictional
trade, restart the backend, and verify that the trade persists. Check another
economy still has its separate portfolio.

By default the schemas are `norx_balanced`, `norx_bull`, `norx_bear`, and
`norx_mania`. They may be viewed in Supabase's SQL editor/table editor by selecting
the schema. **Do not add these schemas to the public Data API exposed schemas.**
Tables have row-level security enabled with no browser access policies. The backend
uses the owning database role; it is the only application component holding the
connection URL. Public API trade listings continue to redact human identities.

`NORX_PG_SCHEMA_PREFIX` can select an independent deployment namespace; it must be
the same for migration and backend. Leave it unset for the defaults. Each active
world uses a dedicated worker-lock connection plus up to four pooled connections
per backend process. Run one backend process initially and place the backend near
the database region to keep simulation/database round trips short.

Keep the SQLite backup until you have verified the PostgreSQL portfolios. Removing
`DATABASE_URL` switches back to SQLite but does **not** copy PostgreSQL changes
back; the two stores are independent after cutover.

## Backups and deployment

Check your Supabase plan's actual backup retention and restore options; creating a
project does not guarantee the backup schedule you want. Set up regular database
backups (and a restore test), and keep credentials in your deployment's secrets.
Supabase free projects may pause while idle. NORX still needs a running Python
backend for agents and token launches; creating a database does not host NORX.

For cloud deployment, set `DATABASE_URL`, leave `NORX_DEV_AUTH=0`, and keep the
Privy App ID consistent. No database credentials belong in the frontend build.

## Development verification

SQLite remains the default when `DATABASE_URL` is absent. Run:

```sh
.venv/bin/python -m unittest discover -q
```

For real PostgreSQL integration tests, set `NORX_TEST_POSTGRES_URL` to a disposable
test database (never your live user database), then run:

```sh
.venv/bin/python -m unittest test_postgres -q
```

Tests create and remove uniquely named test schemas. They cover conservation,
concurrent grants/executions, persistent portfolios, migration and overwrite
refusal, independent worlds, worker ownership, API operations and RLS settings.
