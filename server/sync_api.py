"""
sync_api.py
Sync endpoints (push/pull) using updated_at/deleted_at.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import get_current_user, now_iso, new_id
from .db_server import connect, fetch_one, fetch_all, upsert_rows


router = APIRouter(prefix="/sync", tags=["sync"])

CORE_TABLES = [
    "categories",
    "income",
    "expense",
    "inventory_items",
    "inventory_movements",
    "cattle",
    "vaccinations",
]


def _dt(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


def require_membership(conn, user_id: str, farm_id: str) -> Dict[str, Any]:
    m = fetch_one(conn, "SELECT * FROM memberships WHERE user_id=? AND farm_id=?", (user_id, farm_id))
    if not m:
        raise HTTPException(status_code=403, detail="Sem acesso à fazenda")
    return m


class PushBody(BaseModel):
    farm_id: str
    device_id: str
    last_sync_at: str
    payload: Dict[str, List[Dict[str, Any]]]


@router.post("/push")
def push(body: PushBody, user=Depends(get_current_user)):
    started = now_iso()
    with connect() as conn:
        require_membership(conn, user["id"], body.farm_id)

        log_id = new_id()
        conn.execute(
            "INSERT INTO sync_log(id, user_id, device_id, started_at, status) VALUES(?,?,?,?,?)",
            (log_id, user["id"], body.device_id, started, "STARTED"),
        )

        applied = {t: 0 for t in CORE_TABLES}

        for table in CORE_TABLES:
            rows = body.payload.get(table, []) or []
            if not rows:
                continue

            for r in rows:
                # safety: enforce farm_id from request
                r["farm_id"] = body.farm_id

                # if timestamps missing, set minimal
                r.setdefault("created_at", now_iso())
                r.setdefault("updated_at", now_iso())

                existing = fetch_one(conn, f"SELECT id, updated_at FROM {table} WHERE id=?", (r["id"],))
                if not existing:
                    upsert_rows(conn, table, [r])
                    applied[table] += 1
                    continue

                incoming_u = _dt(r.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)
                existing_u = _dt(existing.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)

                # last write wins; server wins if tie -> only apply if strictly newer
                if incoming_u > existing_u:
                    upsert_rows(conn, table, [r])
                    applied[table] += 1

        finished = now_iso()
        conn.execute(
            "UPDATE sync_log SET finished_at=?, status=? WHERE id=?",
            (finished, "OK", log_id),
        )

    return {"ok": True, "applied": applied, "server_time": finished}


@router.get("/pull")
def pull(farm_id: str, since: str, user=Depends(get_current_user)):
    with connect() as conn:
        require_membership(conn, user["id"], farm_id)

        payload: Dict[str, List[Dict[str, Any]]] = {}
        for table in CORE_TABLES:
            rows = fetch_all(
                conn,
                f"""
                SELECT * FROM {table}
                WHERE farm_id=?
                  AND (
                    updated_at > ?
                    OR (deleted_at IS NOT NULL AND deleted_at > ?)
                  )
                """,
                (farm_id, since, since),
            )
            payload[table] = rows

    return {"ok": True, "server_time": now_iso(), "payload": payload}
