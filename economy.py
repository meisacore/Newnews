"""Persistent USD AMM. All ledger mutations use SQLite write transactions."""

import json
import math
import random
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from personalities import PERSONALITIES, WEALTHY_ENTRANTS, intention

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
            CREATE TABLE IF NOT EXISTS agent_personas(account TEXT PRIMARY KEY, name TEXT NOT NULL, persona TEXT NOT NULL, next_tick INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS agent_grants(account TEXT PRIMARY KEY, amount INTEGER NOT NULL, created_at INTEGER NOT NULL);
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
            self._ensure_personalities(db, now)
            db.commit()

    def _ensure_personalities(self, db, now):
        variants = {
            "value": ("patient_value", "contrarian"),
            "momentum": ("careful_trend", "fomo"),
            "noise": ("retail_noise", "gambler"),
        }
        counts = dict.fromkeys(variants, 0)
        for agent in db.execute(
            "SELECT id,strategy FROM accounts WHERE kind='agent' ORDER BY id"
        ).fetchall():
            strategy = agent["strategy"] if agent["strategy"] in variants else "noise"
            choices = variants[strategy]
            persona = choices[counts[strategy] % len(choices)]
            counts[strategy] += 1
            db.execute(
                "INSERT OR IGNORE INTO agent_personas(account,name,persona) VALUES(?,?,?)",
                (agent["id"], agent["id"].replace("agent-", "Trader "), persona),
            )
        for identity, name, persona, dollars in WEALTHY_ENTRANTS:
            policy = PERSONALITIES[persona]
            created = db.execute(
                "INSERT OR IGNORE INTO accounts VALUES(?,?,?,?,?,?)",
                (
                    identity,
                    dollars * UNIT,
                    "agent",
                    policy.strategy,
                    policy.exposure,
                    policy.activation,
                ),
            )
            if created.rowcount:
                db.execute(
                    "INSERT INTO agent_grants VALUES(?,?,?)",
                    (identity, dollars * UNIT, now),
                )
            db.execute(
                "INSERT OR IGNORE INTO agent_personas(account,name,persona) VALUES(?,?,?)",
                (identity, name, persona),
            )

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
                    "SELECT a.*,p.persona,p.name,p.next_tick FROM accounts a JOIN agent_personas p ON p.account=a.id WHERE a.kind='agent'"
                ).fetchall()
                rng.shuffle(agents)
                for a in agents:
                    policy = PERSONALITIES[a["persona"]]
                    if tick < a["next_tick"] or rng.random() > policy.activation:
                        continue
                    if self._agent_decision(db, a, old["id"], rng):
                        # One global cooldown, not one trade for every sampled coin.
                        db.execute(
                            "UPDATE agent_personas SET next_tick=? WHERE account=?",
                            (tick + rng.randint(*policy.cooldown), a["id"]),
                        )
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

    def _agent_decision(self, db, agent, coin, rng):
        policy = PERSONALITIES[agent["persona"]]
        c = db.execute("SELECT * FROM coins WHERE id=?", (coin,)).fetchone()
        account = db.execute(
            "SELECT cash FROM accounts WHERE id=?", (agent["id"],)
        ).fetchone()
        cash = account["cash"]
        positions = db.execute(
            "SELECT h.qty,c.* FROM holdings h JOIN coins c ON c.id=h.coin WHERE h.account=? AND h.qty>0",
            (agent["id"],),
        ).fetchall()
        held = next((row["qty"] for row in positions if row["id"] == coin), 0)
        exposure = self.amount(c, "sell", held) if held else 0
        equity = cash + sum(self.amount(row, "sell", row["qty"]) for row in positions)
        price = c["cash"] / c["tokens"] / UNIT
        fraction, estimate, explanation = intention(
            agent["persona"], price, c["reference"], c["momentum"], bool(held), rng
        )
        if fraction is None:
            return False
        gap = fraction * equity - exposure
        band = max(UNIT, equity * 0.001)
        reason = f"{agent['name']} · {policy.label}: {explanation}"
        if gap > band:
            budget = int(
                min(gap, cash * rng.uniform(policy.order_min, policy.order_max))
            )
            qty = self._agent_buy_quantity(c, budget, policy, estimate)
            if not qty:
                return False
            self._trade(db, agent["id"], c, "buy", qty, reason)
            return True
        if gap < -band and held:
            qty = (
                held
                if fraction == 0
                else min(held, max(1, int(held * min(1, -gap / max(1, exposure)))))
            )
            if self.amount(c, "sell", qty) > 0:
                self._trade(db, agent["id"], c, "sell", qty, reason)
                return True
        return False

    def _agent_buy_quantity(self, coin, budget, policy, estimate):
        # Both cost tests worsen monotonically with quantity, so size down rather
        # than reject a useful small trade or let any bot empty the pool.
        lo, hi = 0, self.quantity(coin, max(0, budget))
        spot = coin["cash"] / coin["tokens"]
        while lo < hi:
            mid = (lo + hi + 1) // 2
            paid = self.amount(coin, "buy", mid)
            acceptable = paid / mid <= spot * (1 + policy.impact_bps / 10000)
            if policy.disciplined:
                acceptable = (
                    acceptable
                    and estimate is not None
                    and paid / mid <= estimate * UNIT * 0.995
                )
            if acceptable:
                lo = mid
            else:
                hi = mid - 1
        return lo

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
            names = {
                row["account"]: dict(row)
                for row in db.execute("SELECT * FROM agent_personas")
            }

            def public_trade(row):
                value = dict(row)
                bot = names.get(row["account"])
                value["account"] = row["account"] if bot else "Player"
                value["agent_name"] = bot["name"] if bot else "Player"
                value["persona"] = PERSONALITIES[bot["persona"]].label if bot else None
                return value

            trades = [
                public_trade(r)
                for r in db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 30")
            ]
            large_trades = [
                public_trade(r)
                for r in db.execute(
                    "SELECT * FROM trades WHERE amount>=? ORDER BY id DESC LIMIT 10",
                    (1000 * UNIT,),
                )
            ]
            stats = {
                r["account"]: r
                for r in db.execute(
                    "SELECT account,COUNT(*) AS trades,MAX(CASE WHEN side='buy' THEN amount ELSE 0 END) AS biggest_buy FROM trades GROUP BY account"
                )
            }
            agents = []
            for a in db.execute(
                "SELECT a.*,p.name,p.persona,g.amount AS starting_cash FROM accounts a JOIN agent_personas p ON p.account=a.id LEFT JOIN agent_grants g ON g.account=a.id WHERE a.kind='agent'"
            ):
                policy = PERSONALITIES[a["persona"]]
                summary = stats.get(a["id"])
                agents.append(
                    {
                        "id": a["id"],
                        "name": a["name"],
                        "cash": a["cash"],
                        "strategy": policy.strategy,
                        "persona": a["persona"],
                        "personality": policy.label,
                        "disciplined": policy.disciplined,
                        "risk": policy.exposure,
                        "patience": policy.activation,
                        "starting_cash": a["starting_cash"],
                        "trades": summary["trades"] if summary else 0,
                        "biggest_buy": summary["biggest_buy"] if summary else 0,
                    }
                )
            heartbeat = db.execute(
                "SELECT value FROM meta WHERE key='last_tick_at'"
            ).fetchone()
            last_tick = int(heartbeat[0]) if heartbeat else None
            return {
                "api_version": 3,
                "simulation": {
                    "running": last_tick is not None and 0 <= now - last_tick <= 10,
                    "last_tick_at": last_tick,
                },
                "coins": coins,
                "trades": trades,
                "large_trades": large_trades,
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
