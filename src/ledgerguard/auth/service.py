from __future__ import annotations

import sqlite3
from typing import Any

from ledgerguard.audit import service as audit
from ledgerguard.auth import repository
from ledgerguard.auth.passwords import hash_password, verify_password
from ledgerguard.auth.tokens import issue_token, verify_token
from ledgerguard.common.clock import to_iso
from ledgerguard.common.context import Actor, Ctx
from ledgerguard.common.db import Row
from ledgerguard.common.errors import conflict, invalid, unauthorized
from ledgerguard.common.ids import new_id

ROLES = ("customer", "compliance", "admin")
MIN_PASSWORD_LENGTH = 8


def _public(user: Row) -> Row:
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "customer_id": user["customer_id"],
        "active": bool(user["active"]),
    }


# ————————————————————————————————————————

def create_user(ctx: Ctx, email: str, password: str, role: str, customer_id: str | None) -> Row:
    if role not in ROLES:
        raise invalid("invalid_role", "Rol necunoscut.", {"role": role})
    if role == "customer" and not customer_id:
        raise invalid("customer_required", "Utilizatorul client necesită un client asociat.")
    if role != "customer" and customer_id:
        raise invalid("customer_not_allowed", "Doar utilizatorii client au client asociat.")
    if "@" not in email or len(email) > 200:
        raise invalid("invalid_email", "Adresa de email este invalidă.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise invalid("weak_password", f"Parola trebuie să aibă minimum {MIN_PASSWORD_LENGTH} caractere.")
    user_id = new_id("usr")
    with ctx.transaction():
        try:
            repository.insert_user(
                ctx.conn,
                user_id,
                email,
                hash_password(password, ctx.settings.password_iterations),
                role,
                customer_id,
                to_iso(ctx.clock.now()),
            )
        except sqlite3.IntegrityError as error:
            raise conflict("email_taken", "Există deja un utilizator cu acest email.") from error
        audit.record(ctx, "user.created", "user", user_id, {"email": email, "role": role})
    created = repository.get_by_id(ctx.conn, user_id)
    assert created is not None
    return _public(created)


# ————————————————————————————————————————

def user_exists(ctx: Ctx, email: str) -> bool:
    return repository.get_by_email(ctx.conn, email) is not None


# ————————————————————————————————————————

def ensure_user(ctx: Ctx, email: str, password: str, role: str, customer_id: str | None) -> Row:
    existing = repository.get_by_email(ctx.conn, email)
    if existing is not None:
        return _public(existing)
    return create_user(ctx, email, password, role, customer_id)


# ————————————————————————————————————————

def login(ctx: Ctx, email: str, password: str) -> dict[str, Any]:
    user = repository.get_by_email(ctx.conn, email)
    if user is None or not user["active"] or not verify_password(password, user["password_hash"]):
        with ctx.transaction():
            audit.record(ctx, "auth.login_failed", "user", email, {})
        raise unauthorized("Email sau parolă incorectă.")
    token = issue_token(
        ctx.settings.jwt_secret,
        {"sub": user["id"]},
        ctx.clock.now(),
        ctx.settings.jwt_ttl_seconds,
    )
    with ctx.transaction():
        audit.record(
            ctx.as_actor(Actor(user["id"], user["role"], user["customer_id"], user["email"])),
            "auth.login",
            "user",
            user["id"],
            {},
        )
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "customer_id": user["customer_id"],
        "user_id": user["id"],
    }


# ————————————————————————————————————————

def actor_from_header(ctx: Ctx, authorization: str | None) -> Actor:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized()
    claims = verify_token(ctx.settings.jwt_secret, authorization[7:].strip(), ctx.clock.now())
    user = repository.get_by_id(ctx.conn, str(claims.get("sub", "")))
    if user is None or not user["active"]:
        raise unauthorized()
    return Actor(user["id"], user["role"], user["customer_id"], user["email"])


# ————————————————————————————————————————

def describe_actor(actor: Actor) -> dict[str, Any]:
    return {"user_id": actor.user_id, "email": actor.label, "role": actor.role, "customer_id": actor.customer_id}
