"""FastAPI auth dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status

from db.repository.auth import UserRecord, auth_repo
from db.repository.bookings import Actor
from pipeline.request_context import RequestContext, get_request_context, set_request_context


async def get_token_from_request(
    request: Request,
    session_token: Annotated[str | None, Cookie(alias="session_token")] = None,
) -> str | None:
    if session_token:
        return session_token
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(get_token_from_request)],
) -> UserRecord:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    user = await auth_repo.resolve_session(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已失效，请重新登录")
    return user


async def bind_request_context(
    request: Request,
    user: Annotated[UserRecord, Depends(get_current_user)],
) -> RequestContext:
    ctx = get_request_context()
    ctx.user_id = user.id
    ctx.username = user.username
    ctx.role = user.role
    ctx.extra["user_display"] = user.display_name
    set_request_context(ctx)
    return ctx


def actor_from_context(ctx: RequestContext) -> Actor:
    if ctx.user_id is None:
        raise RuntimeError("No user in request context")
    return Actor(id=ctx.user_id, role=ctx.role)


OptionalUser = Annotated[UserRecord | None, Depends(get_token_from_request)]
