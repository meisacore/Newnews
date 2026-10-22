"""Resolve shared database locations independently of a terminal's directory."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def database_path():
    path = Path(os.getenv("NORX_DB", "data/norx.sqlite3")).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
