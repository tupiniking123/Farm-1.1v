"""
FastAPI server (minimal SaaS):
- Auth (register/login) with JWT
- Multi-fazendas: create farm, invite, join
- Sync endpoints: /sync/push and /sync/pull

Run:
  uvicorn server.main:app --reload
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from .db_server import connect, init_schema, fetch_one, fetch_all
from .auth import (
    get_current_user,
    hash_password,
    verify_password,
    create_access_token,
    now_iso,
    new_id,
)
from .sync_api import router as sync_router


app = FastAPI(title="Rural SaaS Server (MVP)")
app.include_router(sync_router)


@app.on_event("startup")
def _startup():
    with connect() as conn:
        init_schema(conn)


class RegisterBody(BaseModel):
    email: EmailStr
    password: str


class LoginBody(BaseModel):
    email: EmailStr
    password: str


@app.post("/auth/register")
def register(body: RegisterBody):
    email = body.email.strip().lower()
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Senha muito curta (mín. 6)")

    with connect() as conn:
        existing = fetch_one(conn, "SELECT id FROM users WHERE email=?", (email,))
        if existing:
            raise HTTPException(status_code=400, detail="E-mail já registrado")

        user_id = new_id()
        conn.execute(
            "INSERT INTO users(id, email, password_hash, created_at) VALUES (?,?,?,?)",
            (user_id, email, hash_password(body.password), now_iso()),
        )

    return {"ok": True, "user_id": user_id}


@app.post("/auth/login")
def login(body: LoginBody):
    email = body.email.strip().lower()
    with connect() as conn:
        user = fetch_one(conn, "SELECT * FROM users WHERE email=?", (email,))
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = create_access_token(user["id"], user["email"])
    return {"access_token": token}


@app.get("/me")
def me(user=Depends(get_current_user)):
    with connect() as conn:
        farms = fetch_all(
            conn,
            """
            SELECT f.id, f.name, f.currency, f.timezone
            FROM farms f
            JOIN memberships m ON m.farm_id=f.id
            WHERE m.user_id=?
            ORDER BY f.name
            """,
            (user["id"],),
        )
    return {"user": user, "farms": farms}


class FarmCreateBody(BaseModel):
    name: str
    currency: str = "BRL"
    timezone: str = "America/Sao_Paulo"


@app.post("/farms")
def create_farm(body: FarmCreateBody, user=Depends(get_current_user)):
    farm_id = new_id()
    ts = now_iso()
    with connect() as conn:
        conn.execute(
            "INSERT INTO farms(id, name, owner_user_id, currency, timezone, created_at) VALUES(?,?,?,?,?,?)",
            (farm_id, body.name, user["id"], body.currency, body.timezone, ts),
        )
        conn.execute(
            "INSERT INTO memberships(id, user_id, farm_id, role, created_at) VALUES(?,?,?,?,?)",
            (new_id(), user["id"], farm_id, "OWNER", ts),
        )

        # seed minimal categories (server side) to match client experience
        cats = [
            ("Ração", 1),
            ("Vacinas", 1),
            ("Mão de obra", 1),
            ("Manutenção", 1),
            ("Combustível", 1),
            ("Imprevistos", 0),
            ("Outros", 0),
        ]
        for name, is_direct in cats:
            conn.execute(
                "INSERT INTO categories(id, farm_id, name, is_direct_cost, created_at, updated_at, deleted_at) VALUES(?,?,?,?,?,?,NULL)",
                (new_id(), farm_id, name, is_direct, ts, ts),
            )

    return {"id": farm_id, "name": body.name, "currency": body.currency, "timezone": body.timezone}


def require_membership(conn, user_id: str, farm_id: str):
    m = fetch_one(conn, "SELECT * FROM memberships WHERE user_id=? AND farm_id=?", (user_id, farm_id))
    if not m:
        raise HTTPException(status_code=403, detail="Sem acesso à fazenda")
    return m


@app.post("/farms/{farm_id}/invite")
def invite(farm_id: str, user=Depends(get_current_user)):
    ts = now_iso()
    code = secrets.token_urlsafe(8)  # short string
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0).isoformat()

    with connect() as conn:
        require_membership(conn, user["id"], farm_id)
        conn.execute(
            "INSERT INTO farm_invites(code, farm_id, created_by_user_id, created_at, expires_at) VALUES(?,?,?,?,?)",
            (code, farm_id, user["id"], ts, expires_at),
        )

    return {"invite_code": code, "expires_at": expires_at}


class JoinBody(BaseModel):
    invite_code: str


@app.post("/farms/join")
def join(body: JoinBody, user=Depends(get_current_user)):
    code = body.invite_code.strip()
    with connect() as conn:
        inv = fetch_one(conn, "SELECT * FROM farm_invites WHERE code=?", (code,))
        if not inv:
            raise HTTPException(status_code=400, detail="Invite inválido")

        # check expiry
        if inv.get("expires_at"):
            exp = datetime.fromisoformat(inv["expires_at"].replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="Invite expirado")

        farm_id = inv["farm_id"]

        # add membership if not exists
        ts = now_iso()
        try:
            conn.execute(
                "INSERT INTO memberships(id, user_id, farm_id, role, created_at) VALUES(?,?,?,?,?)",
                (new_id(), user["id"], farm_id, "STAFF", ts),
            )
        except Exception:
            # unique constraint -> already member
            pass

        farm = fetch_one(conn, "SELECT id, name, currency, timezone FROM farms WHERE id=?", (farm_id,))
    return {"ok": True, "farm": farm}
