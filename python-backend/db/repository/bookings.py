"""Booking and flight data access with permission checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from db.observability import obs_writer
from db.pool import get_pool
from pipeline.request_context import get_request_context

DENY_CONFIRMATION_MSG = "无法处理该确认号，请核对后重试或联系客服。"


@dataclass
class Actor:
    id: UUID
    role: str


@dataclass
class BookingRow:
    id: UUID
    user_id: UUID
    flight_id: UUID
    confirmation_no: str
    seat: str
    status: str
    flight_no: str | None = None
    origin: str | None = None
    destination: str | None = None
    owner_username: str | None = None


class BookingRepository:
    def _is_admin(self, actor: Actor) -> bool:
        return actor.role == "admin"

    async def get_booking_for_actor(
        self, actor: Actor, confirmation_no: str
    ) -> BookingRow | None:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT b.id, b.user_id, b.flight_id, b.confirmation_no, b.seat, b.status,
                       f.flight_no, f.origin, f.destination
                FROM bookings b
                JOIN flights f ON f.id = b.flight_id
                WHERE UPPER(b.confirmation_no) = UPPER($1)
                """,
                confirmation_no.upper(),
            )
        if row is None:
            return None
        if not self._is_admin(actor) and row["user_id"] != actor.id:
            raise PermissionError(DENY_CONFIRMATION_MSG)
        return BookingRow(
            id=row["id"],
            user_id=row["user_id"],
            flight_id=row["flight_id"],
            confirmation_no=row["confirmation_no"],
            seat=row["seat"],
            status=row["status"],
            flight_no=row["flight_no"],
            origin=row["origin"],
            destination=row["destination"],
            owner_username=None,
        )

    def _row_to_booking(self, r: asyncpg.Record) -> BookingRow:
        return BookingRow(
            id=r["id"],
            user_id=r["user_id"],
            flight_id=r["flight_id"],
            confirmation_no=r["confirmation_no"],
            seat=r["seat"],
            status=r["status"],
            flight_no=r["flight_no"],
            origin=r["origin"],
            destination=r["destination"],
            owner_username=r.get("owner_username"),
        )

    async def list_bookings_for_customer(self, actor: Actor, customer_username: str) -> list[BookingRow]:
        if not self._is_admin(actor):
            raise PermissionError("仅管理员可查询指定旅客订单。")
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT b.id, b.user_id, b.flight_id, b.confirmation_no, b.seat, b.status,
                       f.flight_no, f.origin, f.destination, u.username AS owner_username
                FROM bookings b
                JOIN flights f ON f.id = b.flight_id
                JOIN users u ON u.id = b.user_id
                WHERE u.username = $1
                ORDER BY b.created_at DESC
                """,
                customer_username.strip(),
            )
        return [self._row_to_booking(r) for r in rows]

    def _audit_on_behalf_user_id(self, actor: Actor, booking_user_id: UUID) -> UUID | None:
        if self._is_admin(actor) and booking_user_id != actor.id:
            return booking_user_id
        return None

    async def list_bookings_for_actor(self, actor: Actor) -> list[BookingRow]:
        pool = get_pool()
        async with pool.acquire() as conn:
            if self._is_admin(actor):
                rows = await conn.fetch(
                    """
                    SELECT b.id, b.user_id, b.flight_id, b.confirmation_no, b.seat, b.status,
                           f.flight_no, f.origin, f.destination, u.username AS owner_username
                    FROM bookings b
                    JOIN flights f ON f.id = b.flight_id
                    JOIN users u ON u.id = b.user_id
                    ORDER BY b.created_at DESC
                    LIMIT 50
                    """
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT b.id, b.user_id, b.flight_id, b.confirmation_no, b.seat, b.status,
                           f.flight_no, f.origin, f.destination
                    FROM bookings b
                    JOIN flights f ON f.id = b.flight_id
                    WHERE b.user_id = $1
                    ORDER BY b.created_at DESC
                    """,
                    actor.id,
                )
        return [self._row_to_booking(r) for r in rows]

    async def search_flights(
        self, origin: str | None = None, destination: str | None = None
    ) -> list[asyncpg.Record]:
        pool = get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, flight_no, origin, destination, departure_at, arrival_at,
                       seats_available, price_cents, status
                FROM flights
                WHERE ($1::text IS NULL OR origin ILIKE '%' || $1 || '%')
                  AND ($2::text IS NULL OR destination ILIKE '%' || $2 || '%')
                  AND status IN ('scheduled', 'delayed')
                  AND seats_available > 0
                ORDER BY departure_at
                LIMIT 20
                """,
                origin,
                destination,
            )

    async def get_flight_by_number(self, flight_no: str) -> asyncpg.Record | None:
        pool = get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, flight_no, origin, destination, departure_at, arrival_at,
                       seats_available, price_cents, status
                FROM flights
                WHERE flight_no ILIKE $1
                ORDER BY departure_at
                LIMIT 1
                """,
                flight_no,
            )

    async def cancel_booking(
        self,
        actor: Actor,
        confirmation_no: str,
        *,
        on_behalf_of_username: str | None = None,
    ) -> str:
        booking = await self.get_booking_for_actor(actor, confirmation_no)
        if booking is None:
            return DENY_CONFIRMATION_MSG
        await self._validate_on_behalf_customer(actor, booking.user_id, on_behalf_of_username)
        if booking.status == "cancelled":
            return f"确认号 {booking.confirmation_no} 的订单已取消。"

        before = {
            "status": booking.status,
            "flight_id": str(booking.flight_id),
            "seat": booking.seat,
        }
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE bookings SET status = 'cancelled', updated_at = now()
                    WHERE id = $1
                    """,
                    booking.id,
                )
                await conn.execute(
                    """
                    UPDATE flights SET seats_available = seats_available + 1
                    WHERE id = $1
                    """,
                    booking.flight_id,
                )

        ctx = get_request_context()
        await obs_writer.log_audit(
            actor.id,
            actor.role,
            "booking.cancel",
            "booking",
            booking.id,
            trace_id=ctx.trace_id,
            on_behalf_of_user_id=self._audit_on_behalf_user_id(actor, booking.user_id),
            before_state=before,
            after_state={"status": "cancelled"},
        )
        return f"已成功取消航班 {booking.flight_no}，确认号 {booking.confirmation_no}。"

    async def update_seat(
        self,
        actor: Actor,
        confirmation_no: str,
        new_seat: str,
        *,
        on_behalf_of_username: str | None = None,
    ) -> str:
        booking = await self.get_booking_for_actor(actor, confirmation_no)
        if booking is None:
            return DENY_CONFIRMATION_MSG
        await self._validate_on_behalf_customer(actor, booking.user_id, on_behalf_of_username)
        before = {"seat": booking.seat}
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE bookings SET seat = $2, updated_at = now() WHERE id = $1",
                booking.id,
                new_seat,
            )
        ctx = get_request_context()
        await obs_writer.log_audit(
            actor.id,
            actor.role,
            "booking.update_seat",
            "booking",
            booking.id,
            trace_id=ctx.trace_id,
            on_behalf_of_user_id=self._audit_on_behalf_user_id(actor, booking.user_id),
            before_state=before,
            after_state={"seat": new_seat},
        )
        return f"已将确认号 {booking.confirmation_no} 的座位更新为 {new_seat}。"

    async def _validate_on_behalf_customer(
        self,
        actor: Actor,
        booking_user_id: UUID,
        on_behalf_of_username: str | None,
    ) -> None:
        if not on_behalf_of_username or not str(on_behalf_of_username).strip():
            return
        if not self._is_admin(actor):
            raise PermissionError("仅管理员可指定代客旅客。")
        from db.repository.auth import auth_repo

        row = await auth_repo.get_user_by_username(on_behalf_of_username.strip())
        if row is None:
            raise ValueError(f"未知旅客用户名: {on_behalf_of_username}")
        if row["id"] != booking_user_id:
            raise PermissionError(
                f"确认号订单不属于旅客 {on_behalf_of_username}，请核对 on_behalf_of_username。"
            )


booking_repo = BookingRepository()
