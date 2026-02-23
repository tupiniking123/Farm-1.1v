"""
db_local.py
SQLite local database utilities (offline-first).

- Simple helpers: connect, init schema, query/execute
- Upsert by id (UUID string) with updated_at rules handled by caller
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


LOCAL_DB_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "data", "local.db")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def connect(db_path: str = LOCAL_DB_DEFAULT_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def exec_sql(conn: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> None:
    conn.execute(sql, params)


def exec_many(conn: sqlite3.Connection, sql: str, rows: Iterable[Tuple[Any, ...]]) -> None:
    conn.executemany(sql, rows)


def fetch_all(conn: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def fetch_one(conn: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    # Ensure meta row exists
    conn.execute(
        "INSERT OR IGNORE INTO local_meta (id, device_id, last_sync_at) VALUES (1, ?, ?)",
        ("device-local", "1970-01-01T00:00:00+00:00"),
    )
    # Basic settings
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('dark_mode', '1')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('active_farm_id', '')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('server_url', '')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('user_email', '')")


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = fetch_one(conn, "SELECT value FROM settings WHERE key = ?", (key,))
    return (row["value"] if row else default) or default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection) -> Dict[str, Any]:
    return fetch_one(conn, "SELECT * FROM local_meta WHERE id = 1") or {}


def set_last_sync(conn: sqlite3.Connection, iso_ts: str) -> None:
    conn.execute("UPDATE local_meta SET last_sync_at = ? WHERE id = 1", (iso_ts,))


def upsert_rows(
    conn: sqlite3.Connection,
    table: str,
    rows: List[Dict[str, Any]],
    pk: str = "id",
) -> int:
    """
    Generic UPSERT by primary key (default: id).

    Assumes:
    - Table has PRIMARY KEY(pk)
    - Keys in `rows` match table columns
    """
    if not rows:
        return 0

    cols = sorted({k for r in rows for k in r.keys()})
    if pk not in cols:
        raise ValueError(f"Missing primary key '{pk}' in rows for table {table}")

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


SCHEMA_SQL = r"""
-- Meta + settings
CREATE TABLE IF NOT EXISTS local_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  device_id TEXT NOT NULL,
  last_sync_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Local reference for logged user (server auth is the source of truth)
CREATE TABLE IF NOT EXISTS users_local (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS farms (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'BRL',
  timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo'
);

CREATE TABLE IF NOT EXISTS categories (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  name TEXT NOT NULL,
  is_direct_cost INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT,
  FOREIGN KEY (farm_id) REFERENCES farms(id)
);

CREATE TABLE IF NOT EXISTS income (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  date TEXT NOT NULL,
  description TEXT,
  amount REAL NOT NULL,
  source TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT,
  FOREIGN KEY (farm_id) REFERENCES farms(id)
);

CREATE TABLE IF NOT EXISTS expense (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  date TEXT NOT NULL,
  category_id TEXT,
  description TEXT,
  amount REAL NOT NULL,
  vendor TEXT,
  is_unplanned INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT,
  FOREIGN KEY (farm_id) REFERENCES farms(id),
  FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS inventory_items (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('FEED','INPUT','VACCINE')),
  unit TEXT NOT NULL,
  min_level REAL NOT NULL DEFAULT 0,
  expires_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT,
  FOREIGN KEY (farm_id) REFERENCES farms(id)
);

CREATE TABLE IF NOT EXISTS inventory_movements (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  date TEXT NOT NULL,
  qty REAL NOT NULL,
  cost_total REAL NOT NULL DEFAULT 0,
  movement_type TEXT NOT NULL CHECK (movement_type IN ('IN','OUT')),
  note TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT,
  FOREIGN KEY (farm_id) REFERENCES farms(id),
  FOREIGN KEY (item_id) REFERENCES inventory_items(id)
);

CREATE TABLE IF NOT EXISTS cattle (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  birth_date TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT,
  FOREIGN KEY (farm_id) REFERENCES farms(id)
);

CREATE TABLE IF NOT EXISTS vaccinations (
  id TEXT PRIMARY KEY,
  farm_id TEXT NOT NULL,
  cattle_id TEXT NOT NULL,
  vaccine_item_id TEXT NOT NULL,
  date TEXT NOT NULL,
  dose TEXT,
  cost REAL NOT NULL DEFAULT 0,
  next_due_date TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT,
  FOREIGN KEY (farm_id) REFERENCES farms(id),
  FOREIGN KEY (cattle_id) REFERENCES cattle(id),
  FOREIGN KEY (vaccine_item_id) REFERENCES inventory_items(id)
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_income_farm_date ON income(farm_id, date);
CREATE INDEX IF NOT EXISTS idx_expense_farm_date ON expense(farm_id, date);
CREATE INDEX IF NOT EXISTS idx_movements_farm_date ON inventory_movements(farm_id, date);
CREATE INDEX IF NOT EXISTS idx_vaccinations_farm_date ON vaccinations(farm_id, date);
CREATE INDEX IF NOT EXISTS idx_items_farm_type ON inventory_items(farm_id, type);
"""
