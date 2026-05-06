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
    parsed = json.loads(payload)
    # If a previous build saved a failure payload (older code did this),
    # treat it as a miss so the caller retries with the current code path.
    if _is_failure_payload(parsed):
        return None
    return parsed


def set(key: str, value: Any, db_path: Path = DEFAULT_DB_PATH) -> None:
    with _conn(db_path) as c:
        c.execute(
            "INSERT OR REPLACE INTO cached_payloads (key, fetched_at, payload) VALUES (?, ?, ?)",
            (key, int(time.time()), json.dumps(value, default=str, ensure_ascii=False)),
        )


def _is_failure_payload(result: Any) -> bool:
    """Don't cache responses that look like a failure — otherwise a transient
    error gets stuck in SQLite for hours and the user keeps seeing it.
    Empty results are also treated as failure so a misbehaving scraper retries
    on the next call rather than silently returning [] for a day."""
    if isinstance(result, list):
        if not result:
            return True
        return all(
            isinstance(d, dict) and "error" in d and len(d) <= 2 for d in result
        )
    if isinstance(result, dict):
        if "error" in result and len(result) <= 2:
            return True
    return False


def cached(key: str, ttl: int = DEFAULT_TTL_SECONDS):
    """Decorator: cache the JSON-serializable return of a zero-or-more-arg function."""

    def deco(fn):
        def wrapper(*args, **kwargs):
            full_key = f"{key}:{json.dumps([args, kwargs], default=str, sort_keys=True)}"
            hit = get(full_key, ttl=ttl)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            if not _is_failure_payload(result):
                set(full_key, result)
            return result

        return wrapper

    return deco
