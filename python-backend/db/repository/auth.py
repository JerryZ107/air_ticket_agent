"""Authentication repository and session tokens."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg
import bcrypt

from db.observability import obs_writer
from db.pool import get_pool
from pipeline.request_context import get_request_context


@dataclass
class UserRecord:
    id: UUID
    username: str
    display_name: str | None
    role: str


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthRepository:
    async def get_user_by_username(self, username: str) -> asyncpg.Record | None:
        pool = get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT id, username, password_hash, display_name, role FROM users WHERE username = $1",
                username,
            )

    async def verify_login(self, username: str, password: str) -> UserRecord | None:
        row = await self.get_user_by_username(username)
        if row is None:
            return None
        if not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            return None
        return UserRecord(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
        )

    async def create_session(self, user: UserRecord, *, days: int = 7) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires = datetime.now(timezone.utc) + timedelta(days=days)
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO auth_sessions (user_id, token_hash, expires_at)
                VALUES ($1, $2, $3)
                """,
                user.id,
                token_hash,
                expires,
            )
        ctx = get_request_context()
        await obs_writer.log_audit(
            user.id,
            user.role,
            "auth.login",
            "user",
            user.id,
            trace_id=ctx.trace_id,
            after_state={"username": user.username},
        )
        return token

    async def resolve_session(self, token: str) -> UserRecord | None:
        token_hash = _hash_token(token)
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.id, u.username, u.display_name, u.role
                FROM auth_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = $1 AND s.expires_at > now()
                """,
                token_hash,
            )
        if row is None:
            return None
        return UserRecord(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
        )

    async def logout(self, token: str) -> None:
        token_hash = _hash_token(token)
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM auth_sessions WHERE token_hash = $1", token_hash)


auth_repo = AuthRepository()
