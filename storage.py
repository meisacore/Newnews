"""SQLite development storage and private, pooled PostgreSQL world schemas."""

import hashlib
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal

from filelock import Timeout


@dataclass(frozen=True)
class PostgresTarget:
    url: str = field(repr=False)
    schema: str = "norx_balanced"

    def __str__(self):
        return "PostgreSQL world " + self.schema


class Record(dict):
    def __init__(self, names, values):
        self.values_by_index = tuple(
            (int(v) if v == int(v) else float(v)) if isinstance(v, Decimal) else v
            for v in values
        )
        super().__init__(zip(names, self.values_by_index))

    def __getitem__(self, key):
        return (
            self.values_by_index[key]
            if isinstance(key, int)
            else super().__getitem__(key)
        )


def record_factory(cursor):
    names = [column.name for column in (cursor.description or [])]
    return lambda values: Record(names, values)


_pools = {}
_pool_lock = threading.Lock()


def postgres_pool(target):
    import psycopg
    from psycopg import sql
    from psycopg_pool import ConnectionPool

    with _pool_lock:
        if target not in _pools:
            # Schemas are private to the backend role; no tables in Supabase's
            # browser-exposed public schema, and no browser database credentials.
            with psycopg.connect(target.url, autocommit=True, connect_timeout=10) as db:
                with db.transaction():
                    db.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s))",
                        ("norx-schema-" + target.schema,),
                    )
                    db.execute(
                        sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                            sql.Identifier(target.schema)
                        )
                    )

            def configure(db):
                db.execute("SET lock_timeout TO '15s'")
                db.execute("SET statement_timeout TO '30s'")
                db.execute(
                    sql.SQL("SET search_path TO {}").format(
                        sql.Identifier(target.schema)
                    )
                )

            _pools[target] = ConnectionPool(
                target.url,
                min_size=0,
                max_size=4,
                timeout=15,
                kwargs={
                    "autocommit": True,
                    "row_factory": record_factory,
                    "connect_timeout": 10,
                    "prepare_threshold": None,
                },
                configure=configure,
                open=True,
                # Library connection errors can contain host/user details. Keep
                # the pool name independent of credentials.
                name="norx-" + target.schema,
            )
        return _pools[target]


class PostgresConnection:
    def __init__(self, connection, schema):
        self.raw = connection
        self.schema = schema

    def execute(self, query, params=()):
        from psycopg.pq import TransactionStatus

        if query.strip().upper() == "BEGIN IMMEDIATE":
            if self.raw.info.transaction_status == TransactionStatus.IDLE:
                self.raw.execute("BEGIN")
            # All writes to one world serialize just as SQLite BEGIN IMMEDIATE
            # did. Quotes, grants, executions and ticks cannot double-spend.
            return self.raw.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("norx-write-" + self.schema,),
            )
        if query.lstrip().upper().startswith("INSERT OR IGNORE"):
            query = re.sub(r"INSERT OR IGNORE", "INSERT", query, count=1, flags=re.I)
            query += " ON CONFLICT DO NOTHING"
        # SQL is application-authored; values always remain bound parameters.
        query = query.replace("?", "%s")
        if re.match(r"\s*INSERT INTO trades\b", query, re.I):
            cursor = self.raw.execute(query + " RETURNING id", params)
            return InsertResult(cursor.fetchone()[0], cursor.rowcount)
        return self.raw.execute(query, params)

    def executescript(self, script):
        self.execute("BEGIN IMMEDIATE")
        for statement in script.split(";"):
            statement = statement.strip()
            if not statement or statement.startswith("PRAGMA"):
                continue
            statement = statement.replace(
                "id INTEGER PRIMARY KEY", "id BIGSERIAL PRIMARY KEY"
            )
            statement = re.sub(r"\bINTEGER\b", "BIGINT", statement)
            statement = re.sub(r"\bREAL\b", "DOUBLE PRECISION", statement)
            self.raw.execute(statement)
            table = re.match(r"CREATE TABLE IF NOT EXISTS ([a-z_]+)", statement)
            if table:
                # Supabase browser roles cannot access ledger rows, even if a
                # project owner later adds this schema to its exposed schemas.
                self.raw.execute(
                    "ALTER TABLE " + table[1] + " ENABLE ROW LEVEL SECURITY"
                )

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()


@dataclass
class InsertResult:
    lastrowid: int
    rowcount: int


@contextmanager
def connection(target):
    if isinstance(target, PostgresTarget):
        with postgres_pool(target).connection() as db:
            try:
                yield PostgresConnection(db, target.schema)
            finally:
                # Returning an unfinished read/write transaction must never
                # accidentally commit partial ledger changes.
                db.rollback()
    else:
        db = sqlite3.connect(target, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()


@contextmanager
def postgres_worker_lock(target):
    import psycopg

    # Dedicated session connection is essential: use direct/session pooling,
    # not Supabase's transaction pooler for this advisory ownership lock.
    key = int.from_bytes(
        hashlib.sha256(("norx-worker-" + target.schema).encode()).digest()[:8],
        "big",
        signed=True,
    )
    with psycopg.connect(target.url, autocommit=True, connect_timeout=10) as db:
        if not db.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()[0]:
            raise Timeout(str(target))
        try:
            yield db
        finally:
            db.execute("SELECT pg_advisory_unlock(%s)", (key,))
