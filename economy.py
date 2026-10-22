"""Persistent USD AMM. All ledger mutations use SQLite write transactions."""

import json
import math
import random
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

UNIT = 1_000_000  # integer millionths of a dollar
START = 10_000 * UNIT
SUPPLY = 1_000_000
LAUNCH_INTERVAL = 60
LAUNCH_BATCH = 5
PULSE_LIMIT = 60


class Market:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connection() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, cash INTEGER NOT NULL CHECK(cash>=0), kind TEXT NOT NULL, strategy TEXT, risk REAL, patience REAL);
            CREATE TABLE IF NOT EXISTS holdings(account TEXT, coin TEXT, qty INTEGER NOT NULL CHECK(qty>=0), PRIMARY KEY(account,coin));
            CREATE TABLE IF NOT EXISTS coins(id TEXT PRIMARY KEY, name TEXT, symbol TEXT, cash INTEGER CHECK(cash>0), tokens INTEGER CHECK(tokens>0), reference REAL, momentum REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY, ts INTEGER, account TEXT, coin TEXT, side TEXT, qty INTEGER, amount INTEGER, price REAL, reason TEXT);
            CREATE INDEX IF NOT EXISTS trade_time ON trades(coin,ts);
            CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY, account TEXT, coin TEXT, side TEXT, qty INTEGER, amount INTEGER, expires INTEGER, request_id TEXT UNIQUE, result TEXT);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS launches(coin TEXT PRIMARY KEY, created_at INTEGER NOT NULL, seed_cash INTEGER NOT NULL, activity_goal INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS launch_time ON launches(created_at);
            """)
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM coins").fetchone():
                for coin, name, symbol, price in [
                    ("frog", "Moon Frog", "FROG", 0.2),
                    ("rocket", "Rocket Fuel", "RCKT", 1),
                    ("pebble", "Pebble", "PBL", 0.05),
                ]:
                    db.execute(
                        "INSERT INTO coins(id,name,symbol,cash,tokens,reference) VALUES(?,?,?,?,?,?)",
                        (
                            coin,
                            name,
                            symbol,
                            int(100_000 * price * UNIT),
                            100_000,
                            price,
                        ),
                    )
                    db.execute(
                        "INSERT INTO accounts(id,cash,kind) VALUES(?,?,?)",
                        ("treasury", 0, "treasury"),
                    ) if coin == "frog" else None
                    db.execute(
                        "INSERT INTO holdings VALUES(?,?,?)",
                        ("treasury", coin, SUPPLY - 100_000),
                    )
                rng = random.Random(42)
                for i in range(30):
                    strategy = ("value", "momentum", "noise")[i % 3]
                    wealth = (500, 3000, 15000)[(i // 3) % 3]
                    db.execute(
                        "INSERT INTO accounts VALUES(?,?,?,?,?,?)",
                        (
                            f"agent-{i + 1:02}",
                            wealth * UNIT,
                            "agent",
                            strategy,
                            rng.uniform(0.04, 0.18),
                            rng.uniform(0.08, 0.4),
                        ),
                    )
                db.execute("INSERT INTO meta VALUES(?,?)", ("condition", "calm"))
                db.execute("INSERT INTO meta VALUES(?,?)", ("tick", "0"))
            # Additive migration: existing accounts, holdings, pools, and history survive.
            now = int(time.time())
            db.execute(
                "INSERT OR IGNORE INTO launches SELECT id, ?, cash, cash FROM coins",
                (now,),
            )
            db.execute(
                "INSERT OR IGNORE INTO meta VALUES('next_launch_at', ?)",
                (str(now + LAUNCH_INTERVAL),),
            )
            db.execute("INSERT OR IGNORE INTO meta VALUES('launch_sequence', '0')")
            db.commit()

    def _launch_due(self, db, rng, now):
        due = int(
            db.execute("SELECT value FROM meta WHERE key='next_launch_at'").fetchone()[
                0
            ]
        )
        if now < due:
            return []
        sequence = int(
            db.execute("SELECT value FROM meta WHERE key='launch_sequence'").fetchone()[
                0
            ]
        )
        adjectives = (
            "Cosmic",
            "Lunar",
            "Velvet",
            "Solar",
            "Neon",
            "Golden",
            "Tiny",
            "Orbit",
            "Midnight",
            "Pixel",
            "Electric",
            "Crystal",
            "Lucky",
            "Dream",
            "Turbo",
            "Silver",
        )
        nouns = (
            "Otter",
            "Fox",
            "Comet",
            "Panda",
            "Moth",
            "Peach",
            "Whale",
            "Koala",
            "Cloud",
            "Kiwi",
            "Nova",
            "Gecko",
            "Duck",
            "Tiger",
            "Echo",
            "Lotus",
        )
        launched = []
        for _ in range(LAUNCH_BATCH):
            sequence += 1
            adjective, noun = rng.choice(adjectives), rng.choice(nouns)
            coin = f"coin-{sequence:08d}"
            symbol = f"{adjective[:2]}{noun[:2]}{sequence:X}".upper()
            seed_cash = rng.randint(1500, 12000) * UNIT
            pool_tokens = rng.randint(50000, 200000)
            price = seed_cash / pool_tokens / UNIT
            db.execute(
                "INSERT INTO coins(id,name,symbol,cash,tokens,reference) VALUES(?,?,?,?,?,?)",
                (coin, f"{adjective} {noun}", symbol, seed_cash, pool_tokens, price),
            )
            db.execute(
                "INSERT INTO holdings VALUES(?,?,?)",
                ("treasury", coin, SUPPLY - pool_tokens),
            )
            # Explicit fictional launch liquidity; never taken from or credited to users.
            db.execute(
                "INSERT INTO launches VALUES(?,?,?,?)",
                (coin, now, seed_cash, seed_cash),
            )
            launched.append(coin)
        db.execute(
            "UPDATE meta SET value=? WHERE key='launch_sequence'", (str(sequence),)
        )
        # Do not flood the market with missed batches after downtime.
        db.execute(
            "UPDATE meta SET value=? WHERE key='next_launch_at'",
            (str(now + LAUNCH_INTERVAL),),
        )
        return launched

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def account(self, identity):
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO accounts(id,cash,kind) VALUES(?,?,?)",
                (identity, START, "human"),
            )
            a = db.execute(
                "SELECT cash FROM accounts WHERE id=?", (identity,)
            ).fetchone()
            holdings = {
                r["coin"]: r["qty"]
                for r in db.execute(
                    "SELECT coin,qty FROM holdings WHERE account=?", (identity,)
                )
            }
            recent = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM trades WHERE account=? ORDER BY id DESC LIMIT 50",
                    (identity,),
                )
            ]
            return {
                "id": identity,
                "cash": a["cash"] / UNIT,
                "holdings": holdings,
                "trades": recent,
                "positions": [
                    dict(r)
                    for r in db.execute(
                        "SELECT c.id,c.name,c.symbol,h.qty,CAST(c.cash AS REAL)/c.tokens/? AS price FROM holdings h JOIN coins c ON c.id=h.coin WHERE h.account=? AND h.qty>0 ORDER BY c.symbol",
                        (UNIT, identity),
                    )
                ],
            }

    @staticmethod
    def amount(c, side, qty):
        if type(qty) is not int or qty <= 0:
            raise ValueError("Quantity must be a positive whole number")
        x, y = c["tokens"], c["cash"]
        if side == "buy":
            if qty >= x:
                raise ValueError("Insufficient liquidity")
            net = (y * qty + x - qty - 1) // (x - qty)
            return (net * 10000 + 9969) // 9970
        if side != "sell":
            raise ValueError("Invalid side")
        return (y * qty // (x + qty)) * 9970 // 10000

    def quantity(self, c, budget):
        lo, hi = 0, c["tokens"] - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.amount(c, "buy", mid) <= budget:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def quote(self, identity, coin, side, budget=None, qty=None):
        with self.transaction() as db:
            c = db.execute("SELECT * FROM coins WHERE id=?", (coin,)).fetchone()
            if c is None:
                raise ValueError("Unknown coin")
            a = db.execute(
                "SELECT cash FROM accounts WHERE id=?", (identity,)
            ).fetchone()
            if a is None:
                raise ValueError("Account not initialized")
            if side == "buy":
                if type(budget) is not int or budget <= 0 or budget > a["cash"]:
                    raise ValueError("Invalid budget or insufficient USD")
                qty = self.quantity(c, budget)
            if type(qty) is not int or qty <= 0:
                raise ValueError("Amount too small or invalid quantity")
            amount = self.amount(c, side, qty)
            if side == "sell":
                h = db.execute(
                    "SELECT qty FROM holdings WHERE account=? AND coin=?",
                    (identity, coin),
                ).fetchone()
                if not h or h["qty"] < qty:
                    raise ValueError("Insufficient tokens")
            q = {
                "id": str(uuid.uuid4()),
                "coin": coin,
                "side": side,
                "qty": qty,
                "amount": amount,
                "expires": int(time.time()) + 30,
            }
            db.execute(
                "INSERT INTO quotes(id,account,coin,side,qty,amount,expires) VALUES(?,?,?,?,?,?,?)",
                (q["id"], identity, coin, side, qty, amount, q["expires"]),
            )
            return {**q, "usd": amount / UNIT, "slippage_bps": 100}

    def _trade(self, db, identity, c, side, qty, reason):
        amount = self.amount(c, side, qty)
        if amount <= 0:
            raise ValueError("Trade too small")
        if side == "buy":
            updated = db.execute(
                "UPDATE accounts SET cash=cash-? WHERE id=? AND cash>=?",
                (amount, identity, amount),
            )
            if not updated.rowcount:
                raise ValueError("Insufficient USD")
            db.execute(
                "INSERT INTO holdings VALUES(?,?,?) ON CONFLICT(account,coin) DO UPDATE SET qty=qty+excluded.qty",
                (identity, c["id"], qty),
            )
            db.execute(
                "UPDATE coins SET cash=cash+?,tokens=tokens-? WHERE id=?",
                (amount, qty, c["id"]),
            )
        else:
            updated = db.execute(
                "UPDATE holdings SET qty=qty-? WHERE account=? AND coin=? AND qty>=?",
                (qty, identity, c["id"], qty),
            )
            if not updated.rowcount:
                raise ValueError("Insufficient tokens")
            db.execute("UPDATE accounts SET cash=cash+? WHERE id=?", (amount, identity))
            db.execute(
                "UPDATE coins SET cash=cash-?,tokens=tokens+? WHERE id=?",
                (amount, qty, c["id"]),
            )
        # Chart prices are average execution prices, excluding trading fees.
        price = (amount / UNIT / qty) * (0.997 if side == "buy" else 1 / 0.997)
        cur = db.execute(
            "INSERT INTO trades(ts,account,coin,side,qty,amount,price,reason) VALUES(?,?,?,?,?,?,?,?)",
            (int(time.time()), identity, c["id"], side, qty, amount, price, reason),
        )
        return {
            "trade_id": cur.lastrowid,
            "coin": c["id"],
            "side": side,
            "qty": qty,
            "usd": amount / UNIT,
        }

    def execute(self, identity, quote_id, request_id):
        with self.transaction() as db:
            q = db.execute(
                "SELECT * FROM quotes WHERE id=? AND account=?", (quote_id, identity)
            ).fetchone()
            if not q:
                raise ValueError("Unknown quote")
            if q["result"]:
                return json.loads(q["result"])
            if db.execute(
                "SELECT 1 FROM quotes WHERE request_id=?", (request_id,)
            ).fetchone():
                raise ValueError("Request ID already used; request a fresh quote")
            if q["expires"] < time.time():
                raise ValueError("Quote expired; request a new quote")
            c = db.execute("SELECT * FROM coins WHERE id=?", (q["coin"],)).fetchone()
            amount = self.amount(c, q["side"], q["qty"])
            if (q["side"] == "buy" and amount > q["amount"]) or (
                q["side"] == "sell" and amount * 10000 < q["amount"] * 9900
            ):
                raise ValueError("Price moved outside your limit; request a new quote")
            result = self._trade(db, identity, c, q["side"], q["qty"], "Player trade")
            db.execute(
                "UPDATE quotes SET request_id=?,result=? WHERE id=?",
                (request_id, json.dumps(result), quote_id),
            )
            return result

    def tick(self, seed=None, now=None):
        rng = random.Random(seed)
        now = int(time.time()) if now is None else int(now)
        with self.transaction() as db:
            self._launch_due(db, rng, now)
            db.execute(
                "INSERT INTO meta VALUES('last_tick_at', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(now),),
            )
            tick = (
                int(db.execute("SELECT value FROM meta WHERE key='tick'").fetchone()[0])
                + 1
            )
            db.execute("UPDATE meta SET value=? WHERE key='tick'", (str(tick),))
            condition = db.execute(
                "SELECT value FROM meta WHERE key='condition'"
            ).fetchone()[0]
            if rng.random() < 0.008:
                condition = rng.choice(["calm", "optimistic", "stressed"])
                db.execute(
                    "UPDATE meta SET value=? WHERE key='condition'", (condition,)
                )
            drift = {"calm": 0, "optimistic": 0.0003, "stressed": -0.0003}[condition]
            # Bound agent work as launches grow; old positions remain eligible for exits.
            newest = db.execute(
                "SELECT c.* FROM coins c JOIN launches l ON l.coin=c.id ORDER BY l.created_at DESC,c.id DESC LIMIT 40"
            ).fetchall()
            held = db.execute(
                "SELECT DISTINCT c.* FROM coins c JOIN holdings h ON h.coin=c.id JOIN accounts a ON a.id=h.account WHERE a.kind='agent' AND h.qty>0"
            ).fetchall()
            sampled = rng.sample(newest, min(8, len(newest)))
            sampled += rng.sample(held, min(4, len(held)))
            markets = {row["id"]: row for row in sampled}
            for old in markets.values():
                ref = max(
                    0.000001, old["reference"] * math.exp(drift + rng.gauss(0, 0.002))
                )
                db.execute("UPDATE coins SET reference=? WHERE id=?", (ref, old["id"]))
                agents = db.execute(
                    "SELECT * FROM accounts WHERE kind='agent'"
                ).fetchall()
                rng.shuffle(agents)
                for a in agents:
                    if rng.random() > a["patience"]:
                        continue
                    c = db.execute(
                        "SELECT * FROM coins WHERE id=?", (old["id"],)
                    ).fetchone()
                    price = c["cash"] / c["tokens"] / UNIT
                    h = db.execute(
                        "SELECT qty FROM holdings WHERE account=? AND coin=?",
                        (a["id"], c["id"]),
                    ).fetchone()
                    held = h["qty"] if h else 0
                    # Total portfolio value, not just this coin, controls exposure.
                    equity = a["cash"] + sum(
                        r["qty"] * r["cash"] / r["tokens"]
                        for r in db.execute(
                            "SELECT h.qty,c.cash,c.tokens FROM holdings h JOIN coins c ON h.coin=c.id WHERE h.account=?",
                            (a["id"],),
                        )
                    )
                    if a["strategy"] == "value":
                        signal = 0.4 * math.log(
                            ref * math.exp(rng.gauss(0, 0.015)) / price
                        )
                    elif a["strategy"] == "momentum":
                        signal = 3 * c["momentum"] + rng.gauss(0, 0.005)
                    else:
                        signal = rng.gauss(0, 0.035)
                    target = min(1, max(0, 0.35 + signal * 8)) * a["risk"] * equity
                    gap = target - held * price * UNIT
                    reason = f"{a['strategy'].title()}: {'increase' if gap > 0 else 'reduce'} exposure in {condition} conditions"
                    if gap > max(UNIT, equity * 0.002):
                        budget = int(min(gap, a["cash"] * 0.03))
                        qty = self.quantity(c, budget)
                        if qty:
                            self._trade(db, a["id"], c, "buy", qty, reason)
                    elif gap < -max(UNIT, equity * 0.002) and held:
                        qty = min(held, max(1, int(-gap / (price * UNIT))))
                        self._trade(db, a["id"], c, "sell", qty, reason)
                latest = db.execute(
                    "SELECT * FROM coins WHERE id=?", (old["id"],)
                ).fetchone()
                change = math.log(
                    (latest["cash"] / latest["tokens"]) / (old["cash"] / old["tokens"])
                )
                db.execute(
                    "UPDATE coins SET momentum=? WHERE id=?",
                    (0.8 * old["momentum"] + 0.2 * change, old["id"]),
                )
            db.execute(
                "DELETE FROM quotes WHERE result IS NULL AND expires<?",
                (int(time.time()) - 3600,),
            )

    def state(self, selected=None):
        now = int(time.time())
        with self.connection() as db:
            # Aggregate once, instead of querying complete trade histories per coin.
            rows = db.execute(
                """
                SELECT c.*,l.created_at,l.activity_goal,l.seed_cash,
                    COALESCE(t.volume,0) AS total_volume,COALESCE(t.volume_24h,0) AS volume_24h,
                    COALESCE(t.txns,0) AS txns,COALESCE(h.holders,0) AS holders,
                    (SELECT qty FROM holdings WHERE account='treasury' AND coin=c.id) AS treasury_qty,
                    (SELECT price FROM trades WHERE coin=c.id AND ts>=? ORDER BY ts,id LIMIT 1) AS first_price
                FROM coins c JOIN launches l ON l.coin=c.id
                LEFT JOIN (SELECT coin,SUM(amount) AS volume,SUM(CASE WHEN ts>=? THEN amount ELSE 0 END) AS volume_24h,COUNT(*) AS txns FROM trades GROUP BY coin) t ON t.coin=c.id
                LEFT JOIN (SELECT coin,COUNT(*) AS holders FROM holdings WHERE account!='treasury' AND qty>0 GROUP BY coin) h ON h.coin=c.id
                ORDER BY l.created_at DESC,c.id
            """,
                (now - 86400, now - 86400),
            ).fetchall()
            coins = []
            counts = {"new": 0, "stretch": 0, "migrated": 0}
            for r in rows:
                p = r["cash"] / r["tokens"] / UNIT
                circulation = SUPPLY - r["treasury_qty"]
                progress = min(100, r["total_volume"] / r["activity_goal"] * 100)
                stage = (
                    "migrated"
                    if progress >= 100
                    else "stretch"
                    if progress >= 70
                    else "new"
                )
                counts[stage] += 1
                if counts[stage] > PULSE_LIMIT and r["id"] != selected:
                    continue
                coins.append(
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "symbol": r["symbol"],
                        "price": p,
                        "circulating_supply": circulation,
                        "market_cap": p * circulation,
                        "fdv": p * SUPPLY,
                        "volume_24h": r["volume_24h"] / UNIT,
                        "change_24h": (p / r["first_price"] - 1) * 100
                        if r["first_price"]
                        else 0,
                        "pool_usd": r["cash"] / UNIT,
                        "created_at": r["created_at"],
                        "progress": progress,
                        "stage": stage,
                        "txns": r["txns"],
                        "holders": r["holders"],
                        "in_feed": counts[stage] <= PULSE_LIMIT,
                    }
                )
            trades = [
                {
                    **dict(r),
                    "account": r["account"]
                    if r["account"].startswith("agent-")
                    else "Player",
                }
                for r in db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 30")
            ]
            agents = [
                dict(r)
                for r in db.execute(
                    "SELECT id,cash,strategy,risk,patience FROM accounts WHERE kind='agent'"
                )
            ]
            heartbeat = db.execute(
                "SELECT value FROM meta WHERE key='last_tick_at'"
            ).fetchone()
            last_tick = int(heartbeat[0]) if heartbeat else None
            return {
                "api_version": 2,
                "simulation": {
                    "running": last_tick is not None and 0 <= now - last_tick <= 10,
                    "last_tick_at": last_tick,
                },
                "coins": coins,
                "trades": trades,
                "agents": agents,
                "condition": db.execute(
                    "SELECT value FROM meta WHERE key='condition'"
                ).fetchone()[0],
                "simulated": True,
                "pulse_counts": counts,
                "total_coins": sum(counts.values()),
                "next_launch_at": int(
                    db.execute(
                        "SELECT value FROM meta WHERE key='next_launch_at'"
                    ).fetchone()[0]
                ),
                "server_time": now,
                "launch_batch": LAUNCH_BATCH,
            }

    def candles(self, coin, interval=60, limit=120):
        with self.connection() as db:
            if not db.execute("SELECT 1 FROM coins WHERE id=?", (coin,)).fetchone():
                raise ValueError("Unknown coin")
            end = int(time.time()) // interval * interval
            start = end - (limit - 1) * interval
            prev = db.execute(
                "SELECT price FROM trades WHERE coin=? AND ts<? ORDER BY ts DESC,id DESC LIMIT 1",
                (coin, start),
            ).fetchone()
            rows = db.execute(
                "SELECT * FROM trades WHERE coin=? AND ts>=? ORDER BY ts,id",
                (coin, start),
            ).fetchall()
            buckets = {}
            last = prev[0] if prev else None
            for r in rows:
                buckets.setdefault(r["ts"] // interval * interval, []).append(r)
            result = []
            for t in range(start, end + 1, interval):
                trades = buckets.get(t, [])
                if trades:
                    prices = [r["price"] for r in trades]
                    last = prices[-1]
                    result.append(
                        {
                            "time": t,
                            "open": prices[0],
                            "high": max(prices),
                            "low": min(prices),
                            "close": last,
                            "volume": sum(r["amount"] for r in trades) / UNIT,
                        }
                    )
                elif last is not None:
                    result.append(
                        {
                            "time": t,
                            "open": last,
                            "high": last,
                            "low": last,
                            "close": last,
                            "volume": 0,
                        }
                    )
            return result
