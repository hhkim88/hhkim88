from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DEFAULT_TTL_SECONDS = 24 * 60 * 60
DEFAULT_DB_PATH = Path(os.environ.get("COMPANY_SEARCH_DB", str(Path.home() / ".company_search.db")))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cached_payloads (
    key TEXT PRIMARY KEY,
    fetched_at INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fetched_at ON cached_payloads(fetched_at);
"""


@contextmanager
def _conn(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def get(key: str, ttl: int = DEFAULT_TTL_SECONDS, db_path: Path = DEFAULT_DB_PATH) -> Any | None:
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT fetched_at, payload FROM cached_payloads WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    fetched_at, payload = row
    if time.time() - fetched_at > ttl:
        return None
    return json.loads(payload)


def set(key: str, value: Any, db_path: Path = DEFAULT_DB_PATH) -> None:
    with _conn(db_path) as c:
        c.execute(
            "INSERT OR REPLACE INTO cached_payloads (key, fetched_at, payload) VALUES (?, ?, ?)",
            (key, int(time.time()), json.dumps(value, default=str, ensure_ascii=False)),
        )


def cached(key: str, ttl: int = DEFAULT_TTL_SECONDS):
    """Decorator: cache the JSON-serializable return of a zero-or-more-arg function."""

    def deco(fn):
        def wrapper(*args, **kwargs):
            full_key = f"{key}:{json.dumps([args, kwargs], default=str, sort_keys=True)}"
            hit = get(full_key, ttl=ttl)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            set(full_key, result)
            return result

        return wrapper

    return deco
