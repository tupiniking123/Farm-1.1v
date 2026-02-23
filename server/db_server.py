"""
db_server.py
Minimal SQLite access for the FastAPI server.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

SERVER_DB_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "data", "server.db")
MODELS_SQL_PATH = os.path.join(os.path.dirname(__file__), "models_server.sql")


@contextmanager
def connect(db_path: str = SERVER_DB_DEFAULT_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    with open(MODELS_SQL_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())


def fetch_one(conn: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_all(conn: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def upsert_rows(conn: sqlite3.Connection, table: str, rows: List[Dict[str, Any]], pk: str = "id") -> int:
    if not rows:
        return 0
    cols = sorted({k for r in rows for k in r.keys()})
    if pk not in cols:
        raise ValueError(f"Missing pk '{pk}' for table {table}")

    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    update_cols = [c for c in cols if c != pk]
    set_clause = ", ".join([f"{c}=excluded.{c}" for c in update_cols])

    sql = f"""
        INSERT INTO {table} ({col_list})
        VALUES ({placeholders})
        ON CONFLICT({pk}) DO UPDATE SET
        {set_clause}
    """.strip()

    params = [tuple((r.get(c) for c in cols)) for r in rows]
    conn.executemany(sql, params)
    return len(rows)
