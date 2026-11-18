from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ledgerguard.accounts import service as accounts
from ledgerguard.app.deps import anonymous_ctx, auth_ctx, limit
from ledgerguard.auth import service
from ledgerguard.common.context import Ctx

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


# ————————————————————————————————————————

class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)


# ————————————————————————————————————————

class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: str
    customer_id: str | None = None


# ————————————————————————————————————————

@router.post("/auth/login", dependencies=[Depends(limit("login"))])
def login(body: LoginIn, ctx: Ctx = Depends(anonymous_ctx)) -> dict[str, Any]:
    return service.login(ctx, body.email, body.password)


# ————————————————————————————————————————

@router.get("/auth/me")
def me(ctx: Ctx = Depends(auth_ctx("customer", "compliance", "admin"))) -> dict[str, Any]:
    return service.describe_actor(ctx.actor)


# ————————————————————————————————————————

@router.post("/customers", status_code=201)
def create_customer(body: CustomerIn, ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    with ctx.transaction():
        customer = accounts.create_customer(ctx, body.name)
        user = service.create_user(ctx, body.email, body.password, "customer", customer["id"])
    return {"customer": customer, "user": user}


# ————————————————————————————————————————

@router.post("/users", status_code=201)
def create_user(body: UserIn, ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    return service.create_user(ctx, body.email, body.password, body.role, body.customer_id)
