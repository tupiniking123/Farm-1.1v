"""
sync_client.py
Light sync: push/pull using updated_at/deleted_at.

Conflict rule:
- "last write wins" by updated_at
- server wins if tie
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests

from db_local import fetch_all, get_meta, set_last_sync, upsert_rows, now_iso


CORE_TABLES = [
    "categories",
    "income",
    "expense",
    "inventory_items",
    "inventory_movements",
    "cattle",
    "vaccinations",
]


def _changed_rows(conn, table: str, farm_id: str, since_iso: str) -> List[Dict[str, Any]]:
    # include soft-deleted rows if deleted_at > since
    sql = f"""
    SELECT * FROM {table}
    WHERE farm_id=?
      AND (
        updated_at > ?
        OR (deleted_at IS NOT NULL AND deleted_at > ?)
      )
    """
    return fetch_all(conn, sql, (farm_id, since_iso, since_iso))


def push(conn, server_url: str, token: str, farm_id: str) -> Dict[str, Any]:
    meta = get_meta(conn)
    device_id = meta.get("device_id", "device-local")
    last_sync_at = meta.get("last_sync_at", "1970-01-01T00:00:00+00:00")

    payload = {t: _changed_rows(conn, t, farm_id, last_sync_at) for t in CORE_TABLES}

    url = server_url.rstrip("/") + "/sync/push"
    resp = requests.post(
        url,
        json={
            "farm_id": farm_id,
            "device_id": device_id,
            "last_sync_at": last_sync_at,
            "payload": payload,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def pull(conn, server_url: str, token: str, farm_id: str, since_iso: str) -> Dict[str, Any]:
    url = server_url.rstrip("/") + "/sync/pull"
    resp = requests.get(
        url,
        params={"farm_id": farm_id, "since": since_iso},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def apply_pull(conn, data: Dict[str, Any]) -> None:
    payload = data.get("payload", {}) or {}
    for table, rows in payload.items():
        if table in CORE_TABLES and rows:
            upsert_rows(conn, table, rows)


def sync_now(conn, server_url: str, token: str, farm_id: str) -> Dict[str, Any]:
    """
    1) push local changes since last_sync_at
    2) pull remote changes since last_sync_at
    3) apply pull upserts
    4) set last_sync_at to server_time
    """
    meta = get_meta(conn)
    last_sync_at = meta.get("last_sync_at", "1970-01-01T00:00:00+00:00")

    push_result = push(conn, server_url, token, farm_id)
    server_time = push_result.get("server_time") or now_iso()

    pull_result = pull(conn, server_url, token, farm_id, since_iso=last_sync_at)
    apply_pull(conn, pull_result)

    set_last_sync(conn, server_time)

    return {
        "push": push_result,
        "pull": pull_result,
        "server_time": server_time,
    }
