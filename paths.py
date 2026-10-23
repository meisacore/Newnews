"""Resolve shared database locations independently of a terminal's directory."""

import os
import re
from storage import PostgresTarget
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parent


def database_path():
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        if not url.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")
        parsed = urlsplit(url)
        if parsed.port == 6543:
            raise ValueError(
                "Use the Supabase session pooler on port 5432, not transaction pooling on 6543"
            )
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            query = parse_qs(parsed.query)
            sslmode = query.setdefault("sslmode", ["require"])[0]
            if sslmode not in ("require", "verify-ca", "verify-full"):
                raise ValueError("Remote PostgreSQL requires TLS")
            url = urlunsplit(parsed._replace(query=urlencode(query, doseq=True)))
        prefix = os.getenv("NORX_PG_SCHEMA_PREFIX", "norx_")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,35}", prefix):
            raise ValueError("Invalid NORX_PG_SCHEMA_PREFIX")
        return PostgresTarget(url, prefix + "balanced")
    path = Path(os.getenv("NORX_DB", "data/norx.sqlite3")).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def world_path(target, world):
    from scenarios import SCENARIOS

    if world not in SCENARIOS:
        raise ValueError("Unknown economy")
    if isinstance(target, PostgresTarget):
        prefix = target.schema.removesuffix("balanced")
        return PostgresTarget(target.url, prefix + world)
    path = Path(target)
    return (
        path
        if world == "balanced"
        else path.with_name(path.stem + "-" + world + path.suffix)
    )
