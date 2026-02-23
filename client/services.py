"""
services.py
Business logic in small, named functions (no heavy layers).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid

import pandas as pd

from db_local import fetch_all, fetch_one, now_iso, upsert_rows, exec_sql


def new_id() -> str:
    return str(uuid.uuid4())


def parse_date(d: str) -> datetime:
    # expects YYYY-MM-DD
    return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def ensure_default_categories(conn, farm_id: str) -> None:
    existing = fetch_one(conn, "SELECT id FROM categories WHERE farm_id=? AND deleted_at IS NULL LIMIT 1", (farm_id,))
    if existing:
        return

    ts = now_iso()
    cats = [
        ("Ração", 1),
        ("Vacinas", 1),
        ("Mão de obra", 1),
        ("Manutenção", 1),
        ("Combustível", 1),
        ("Imprevistos", 0),
        ("Outros", 0),
    ]
    rows = []
    for name, is_direct_cost in cats:
        rows.append(
            dict(
                id=new_id(),
                farm_id=farm_id,
                name=name,
                is_direct_cost=is_direct_cost,
                created_at=ts,
                updated_at=ts,
                deleted_at=None,
            )
        )
    upsert_rows(conn, "categories", rows)


def create_farm_local(conn, name: str, currency: str = "BRL", timezone_str: str = "America/Sao_Paulo") -> str:
    farm_id = new_id()
    upsert_rows(conn, "farms", [dict(id=farm_id, name=name, currency=currency, timezone=timezone_str)])
    ensure_default_categories(conn, farm_id)
    return farm_id


def list_farms_local(conn) -> List[Dict[str, Any]]:
    return fetch_all(conn, "SELECT * FROM farms ORDER BY name")


def list_categories(conn, farm_id: str) -> List[Dict[str, Any]]:
    return fetch_all(
        conn,
        "SELECT * FROM categories WHERE farm_id=? AND deleted_at IS NULL ORDER BY name",
        (farm_id,),
    )


def add_income(conn, farm_id: str, date: str, description: str, amount: float, source: str) -> str:
    ts = now_iso()
    inc_id = new_id()
    upsert_rows(
        conn,
        "income",
        [
            dict(
                id=inc_id,
                farm_id=farm_id,
                date=date,
                description=description,
                amount=float(amount),
                source=source,
                created_at=ts,
                updated_at=ts,
                deleted_at=None,
            )
        ],
    )
    return inc_id


def add_expense(
    conn,
    farm_id: str,
    date: str,
    category_id: Optional[str],
    description: str,
    amount: float,
    vendor: str,
    is_unplanned: bool,
) -> str:
    ts = now_iso()
    exp_id = new_id()
    upsert_rows(
        conn,
        "expense",
        [
            dict(
                id=exp_id,
                farm_id=farm_id,
                date=date,
                category_id=category_id,
                description=description,
                amount=float(amount),
                vendor=vendor,
                is_unplanned=1 if is_unplanned else 0,
                created_at=ts,
                updated_at=ts,
                deleted_at=None,
            )
        ],
    )
    return exp_id


def soft_delete(conn, table: str, row_id: str) -> None:
    ts = now_iso()
    exec_sql(conn, f"UPDATE {table} SET deleted_at=?, updated_at=? WHERE id=?", (ts, ts, row_id))


def upsert_inventory_item(
    conn,
    farm_id: str,
    name: str,
    type_: str,
    unit: str,
    min_level: float,
    expires_at: Optional[str] = None,
    item_id: Optional[str] = None,
) -> str:
    ts = now_iso()
    iid = item_id or new_id()
    upsert_rows(
        conn,
        "inventory_items",
        [
            dict(
                id=iid,
                farm_id=farm_id,
                name=name,
                type=type_,
                unit=unit,
                min_level=float(min_level or 0),
                expires_at=expires_at,
                created_at=ts if not item_id else fetch_one(conn, "SELECT created_at FROM inventory_items WHERE id=?", (iid,))["created_at"],
                updated_at=ts,
                deleted_at=None,
            )
        ],
    )
    return iid


def add_inventory_movement(
    conn,
    farm_id: str,
    item_id: str,
    date: str,
    qty: float,
    cost_total: float,
    movement_type: str,
    note: str,
) -> str:
    ts = now_iso()
    mid = new_id()
    upsert_rows(
        conn,
        "inventory_movements",
        [
            dict(
                id=mid,
                farm_id=farm_id,
                item_id=item_id,
                date=date,
                qty=float(qty),
                cost_total=float(cost_total or 0),
                movement_type=movement_type,
                note=note,
                created_at=ts,
                updated_at=ts,
                deleted_at=None,
            )
        ],
    )
    return mid


def upsert_cattle(
    conn,
    farm_id: str,
    tag: str,
    birth_date: Optional[str],
    notes: str,
    cattle_id: Optional[str] = None,
) -> str:
    ts = now_iso()
    cid = cattle_id or new_id()
    created_at = ts
    if cattle_id:
        row = fetch_one(conn, "SELECT created_at FROM cattle WHERE id=?", (cid,))
        created_at = row["created_at"] if row else ts
    upsert_rows(
        conn,
        "cattle",
        [
            dict(
                id=cid,
                farm_id=farm_id,
                tag=tag,
                birth_date=birth_date,
                notes=notes,
                created_at=created_at,
                updated_at=ts,
                deleted_at=None,
            )
        ],
    )
    return cid


def add_vaccination(
    conn,
    farm_id: str,
    cattle_id: str,
    vaccine_item_id: str,
    date: str,
    dose: str,
    cost: float,
    next_due_date: Optional[str],
) -> str:
    ts = now_iso()
    vid = new_id()
    upsert_rows(
        conn,
        "vaccinations",
        [
            dict(
                id=vid,
                farm_id=farm_id,
                cattle_id=cattle_id,
                vaccine_item_id=vaccine_item_id,
                date=date,
                dose=dose,
                cost=float(cost or 0),
                next_due_date=next_due_date,
                created_at=ts,
                updated_at=ts,
                deleted_at=None,
            )
        ],
    )
    return vid


# ----------------------------
# Queries for dashboards/alerts
# ----------------------------

def df_income(conn, farm_id: str, start: str, end: str) -> pd.DataFrame:
    rows = fetch_all(
        conn,
        """
        SELECT * FROM income
        WHERE farm_id=? AND deleted_at IS NULL AND date BETWEEN ? AND ?
        ORDER BY date
        """,
        (farm_id, start, end),
    )
    return pd.DataFrame(rows)


def df_expense(conn, farm_id: str, start: str, end: str) -> pd.DataFrame:
    rows = fetch_all(
        conn,
        """
        SELECT e.*, c.name as category_name, COALESCE(c.is_direct_cost,0) as is_direct_cost
        FROM expense e
        LEFT JOIN categories c ON c.id = e.category_id
        WHERE e.farm_id=? AND e.deleted_at IS NULL AND e.date BETWEEN ? AND ?
        ORDER BY e.date
        """,
        (farm_id, start, end),
    )
    return pd.DataFrame(rows)


def df_inventory_items(conn, farm_id: str) -> pd.DataFrame:
    rows = fetch_all(
        conn,
        "SELECT * FROM inventory_items WHERE farm_id=? AND deleted_at IS NULL ORDER BY type, name",
        (farm_id,),
    )
    return pd.DataFrame(rows)


def df_inventory_movements(conn, farm_id: str, start: str, end: str) -> pd.DataFrame:
    rows = fetch_all(
        conn,
        """
        SELECT m.*, i.name AS item_name, i.type AS item_type, i.unit AS unit
        FROM inventory_movements m
        JOIN inventory_items i ON i.id = m.item_id
        WHERE m.farm_id=? AND m.deleted_at IS NULL AND m.date BETWEEN ? AND ?
        ORDER BY m.date
        """,
        (farm_id, start, end),
    )
    return pd.DataFrame(rows)


def df_cattle(conn, farm_id: str) -> pd.DataFrame:
    rows = fetch_all(
        conn,
        "SELECT * FROM cattle WHERE farm_id=? AND deleted_at IS NULL ORDER BY tag",
        (farm_id,),
    )
    return pd.DataFrame(rows)


def df_vaccinations(conn, farm_id: str, start: str, end: str) -> pd.DataFrame:
    rows = fetch_all(
        conn,
        """
        SELECT v.*, c.tag AS cattle_tag, i.name AS vaccine_name
        FROM vaccinations v
        JOIN cattle c ON c.id = v.cattle_id
        JOIN inventory_items i ON i.id = v.vaccine_item_id
        WHERE v.farm_id=? AND v.deleted_at IS NULL AND v.date BETWEEN ? AND ?
        ORDER BY v.date DESC
        """,
        (farm_id, start, end),
    )
    return pd.DataFrame(rows)


def inventory_balance(conn, farm_id: str) -> pd.DataFrame:
    rows = fetch_all(
        conn,
        """
        SELECT
          i.id AS item_id,
          i.name,
          i.type,
          i.unit,
          i.min_level,
          i.expires_at,
          SUM(CASE WHEN m.movement_type='IN' THEN m.qty ELSE -m.qty END) AS balance
        FROM inventory_items i
        LEFT JOIN inventory_movements m ON m.item_id = i.id AND m.deleted_at IS NULL
        WHERE i.farm_id=? AND i.deleted_at IS NULL
        GROUP BY i.id, i.name, i.type, i.unit, i.min_level, i.expires_at
        ORDER BY i.type, i.name
        """,
        (farm_id,),
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["balance"] = df["balance"].fillna(0.0)
    return df


def compute_kpis(conn, farm_id: str, start: str, end: str) -> Dict[str, float]:
    inc = fetch_one(
        conn,
        """
        SELECT COALESCE(SUM(amount),0) AS total
        FROM income WHERE farm_id=? AND deleted_at IS NULL AND date BETWEEN ? AND ?
        """,
        (farm_id, start, end),
    )["total"]
    exp = fetch_one(
        conn,
        """
        SELECT COALESCE(SUM(amount),0) AS total
        FROM expense WHERE farm_id=? AND deleted_at IS NULL AND date BETWEEN ? AND ?
        """,
        (farm_id, start, end),
    )["total"]

    direct = fetch_one(
        conn,
        """
        SELECT COALESCE(SUM(e.amount),0) AS total
        FROM expense e
        JOIN categories c ON c.id=e.category_id
        WHERE e.farm_id=? AND e.deleted_at IS NULL AND e.date BETWEEN ? AND ? AND COALESCE(c.is_direct_cost,0)=1
        """,
        (farm_id, start, end),
    )["total"]

    gross_profit = float(inc) - float(direct)
    net_profit = float(inc) - float(exp)
    margin = (net_profit / float(inc) * 100.0) if float(inc) > 0 else 0.0
    return {
        "income": float(inc),
        "expense": float(exp),
        "gross_profit": float(gross_profit),
        "net_profit": float(net_profit),
        "margin": float(margin),
    }


def alerts(conn, farm_id: str) -> Dict[str, pd.DataFrame]:
    today = datetime.now(timezone.utc).date()
    low_stock = inventory_balance(conn, farm_id)
    if not low_stock.empty:
        low_stock = low_stock[low_stock["balance"] < low_stock["min_level"]].copy()

    expiring = inventory_balance(conn, farm_id)
    if not expiring.empty:
        expiring = expiring[expiring["expires_at"].notna()].copy()
        expiring["expires_at_dt"] = pd.to_datetime(expiring["expires_at"], errors="coerce").dt.date
        expiring = expiring[(expiring["expires_at_dt"] <= (today + timedelta(days=30)))].copy()

    vaccines_due_rows = fetch_all(
        conn,
        """
        SELECT v.*, c.tag AS cattle_tag, i.name AS vaccine_name
        FROM vaccinations v
        JOIN cattle c ON c.id=v.cattle_id
        JOIN inventory_items i ON i.id=v.vaccine_item_id
        WHERE v.farm_id=? AND v.deleted_at IS NULL AND v.next_due_date IS NOT NULL
        """,
        (farm_id,),
    )
    vaccines_due = pd.DataFrame(vaccines_due_rows)
    if not vaccines_due.empty:
        vaccines_due["next_due_dt"] = pd.to_datetime(vaccines_due["next_due_date"], errors="coerce").dt.date
        vaccines_due = vaccines_due[(vaccines_due["next_due_dt"] <= (today + timedelta(days=7)))].copy()
        vaccines_due = vaccines_due.sort_values("next_due_date")

    anomalies = anomalies_expense(conn, farm_id)

    return {
        "low_stock": low_stock,
        "expiring": expiring.drop(columns=["expires_at_dt"], errors="ignore"),
        "vaccines_due": vaccines_due.drop(columns=["next_due_dt"], errors="ignore"),
        "anomalies": anomalies,
    }


def anomalies_expense(conn, farm_id: str) -> pd.DataFrame:
    """
    Anomaly rule:
    current month expense per category > 1.5 * avg(last 3 months) for that category.
    """
    today = datetime.now(timezone.utc).date()
    current_month_start = today.replace(day=1)
    # last 3 months window: from 1st day of (current_month - 3) to day before current month
    # approx using 90 days (good enough for MVP)
    last3_start = current_month_start - timedelta(days=90)
    last3_end = current_month_start - timedelta(days=1)

    rows = fetch_all(
        conn,
        """
        SELECT
          COALESCE(c.name,'Sem categoria') AS category,
          SUM(CASE WHEN e.date >= ? AND e.date <= ? THEN e.amount ELSE 0 END) AS current_month,
          SUM(CASE WHEN e.date >= ? AND e.date <= ? THEN e.amount ELSE 0 END) AS last3_total
        FROM expense e
        LEFT JOIN categories c ON c.id = e.category_id
        WHERE e.farm_id=? AND e.deleted_at IS NULL
        GROUP BY COALESCE(c.name,'Sem categoria')
        """,
        (
            current_month_start.isoformat(), today.isoformat(),
            last3_start.isoformat(), last3_end.isoformat(),
            farm_id,
        ),
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["last3_avg"] = df["last3_total"] / 3.0
    df["threshold"] = df["last3_avg"] * 1.5
    out = df[(df["current_month"] > df["threshold"]) & (df["last3_avg"] > 0)].copy()
    out = out.sort_values("current_month", ascending=False)
    return out
