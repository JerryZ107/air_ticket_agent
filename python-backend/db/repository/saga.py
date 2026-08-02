"""Rebooking saga (in-place update, confirmation number unchanged)."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from db.observability import obs_writer
from db.pool import get_pool
from db.repository.bookings import Actor, BookingRepository, DENY_CONFIRMATION_MSG

booking_repo = BookingRepository()


class SeatUnavailableError(Exception):
    """事务内确认目标航班余票不足（并发下预检可能过时）。"""


class RebookingSaga:
    async def run(
        self,
        actor: Actor,
        confirmation_no: str,
        new_flight_no: str,
        new_seat: str = "自动分配",
        *,
        on_behalf_of_username: str | None = None,
    ) -> str:
        booking = await booking_repo.get_booking_for_actor(actor, confirmation_no)
        if booking is None:
            return DENY_CONFIRMATION_MSG
        await booking_repo._validate_on_behalf_customer(actor, booking.user_id, on_behalf_of_username)
        if booking.status != "confirmed":
            return f"确认号 {booking.confirmation_no} 当前状态为 {booking.status}，无法改签。"

        new_flight = await booking_repo.get_flight_by_number(new_flight_no)
        if new_flight is None:
            return f"未找到航班 {new_flight_no}。"
        if new_flight["seats_available"] < 1:
            return f"航班 {new_flight_no} 已无空余座位。"

        saga_id = uuid4()
        pool = get_pool()
        ctx_trace = None
        try:
            from pipeline.request_context import get_request_context

            ctx_trace = get_request_context().trace_id
        except Exception:
            pass

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO booking_sagas (id, booking_id, actor_id, target_flight_id, status)
                    VALUES ($1, $2, $3, $4, 'running')
                    """,
                    saga_id,
                    booking.id,
                    actor.id,
                    new_flight["id"],
                )
                snap = {
                    "flight_id": str(booking.flight_id),
                    "seat": booking.seat,
                }
                await conn.execute(
                    """
                    INSERT INTO booking_saga_steps (saga_id, step_no, action, payload, status)
                    VALUES ($1, 1, 'lock_new_seat', $2::jsonb, 'done')
                    """,
                    saga_id,
                    json.dumps({"flight_id": str(new_flight["id"]), "seat": new_seat}),
                )
                await conn.execute(
                    """
                    INSERT INTO booking_saga_steps (saga_id, step_no, action, payload, status)
                    VALUES ($1, 2, 'snapshot_old', $2::jsonb, 'done')
                    """,
                    saga_id,
                    json.dumps(snap),
                )
                try:
                    # 真正的并发防线：在事务内原子扣减并校验影响行数。
                    # 预检（seats_available < 1）在事务外，可能已过时，以这里为准。
                    locked = await conn.execute(
                        """
                        UPDATE flights SET seats_available = seats_available - 1
                        WHERE id = $1 AND seats_available > 0
                        """,
                        new_flight["id"],
                    )
                    if locked != "UPDATE 1":
                        raise SeatUnavailableError(new_flight["flight_no"])
                    await conn.execute(
                        """
                        UPDATE flights SET seats_available = seats_available + 1
                        WHERE id = $1
                        """,
                        booking.flight_id,
                    )
                    await conn.execute(
                        """
                        UPDATE bookings
                        SET flight_id = $2, seat = $3, updated_at = now()
                        WHERE id = $1
                        """,
                        booking.id,
                        new_flight["id"],
                        new_seat,
                    )
                    # 座位消费留痕（审计性记录；唯一性由 flights.seats_available 原子递减保证）
                    await conn.execute(
                        """
                        INSERT INTO seat_locks (flight_id, seat, saga_id, booking_id, locked_until, status)
                        VALUES ($1, $2, $3, $4, now() + interval '30 days', 'consumed')
                        """,
                        new_flight["id"],
                        new_seat,
                        saga_id,
                        booking.id,
                    )
                    await conn.execute(
                        """
                        INSERT INTO booking_saga_steps (saga_id, step_no, action, payload, status)
                        VALUES ($1, 3, 'update_booking', $2::jsonb, 'done')
                        """,
                        saga_id,
                        json.dumps({"confirmation_no": booking.confirmation_no}),
                    )
                    await conn.execute(
                        "UPDATE booking_sagas SET status = 'completed', finished_at = now() WHERE id = $1",
                        saga_id,
                    )
                except SeatUnavailableError as exc:
                    await conn.execute(
                        """
                        INSERT INTO booking_saga_steps (saga_id, step_no, action, payload, status, error_message)
                        VALUES ($1, 3, 'update_booking', '{}'::jsonb, 'failed', $2)
                        """,
                        saga_id,
                        str(exc),
                    )
                    await conn.execute(
                        "UPDATE booking_sagas SET status = 'compensated', finished_at = now() WHERE id = $1",
                        saga_id,
                    )
                    return (
                        f"航班 {exc.args[0]} 余票已售罄，未能改签；"
                        f"您的原航班预订未做任何变更，确认号 {booking.confirmation_no} 仍然有效。"
                    )
                except Exception as exc:
                    await conn.execute(
                        """
                        INSERT INTO booking_saga_steps (saga_id, step_no, action, payload, status, error_message)
                        VALUES ($1, 3, 'update_booking', '{}'::jsonb, 'failed', $2)
                        """,
                        saga_id,
                        str(exc),
                    )
                    await conn.execute(
                        "UPDATE booking_sagas SET status = 'compensated', finished_at = now() WHERE id = $1",
                        saga_id,
                    )
                    return (
                        f"改签未完成，您的原航班预订未做任何变更，确认号 {booking.confirmation_no} 仍然有效。"
                    )

        await obs_writer.log_audit(
            actor.id,
            actor.role,
            "booking.rebook",
            "booking",
            booking.id,
            trace_id=ctx_trace,
            on_behalf_of_user_id=booking_repo._audit_on_behalf_user_id(actor, booking.user_id),
            before_state=snap,
            after_state={
                "flight_id": str(new_flight["id"]),
                "flight_no": new_flight["flight_no"],
                "seat": new_seat,
                "confirmation_no": booking.confirmation_no,
            },
        )
        return (
            f"已改签至 {new_flight['flight_no']}，{new_flight['origin']} -> {new_flight['destination']}。"
            f"座位：{new_seat}，确认号 {booking.confirmation_no}（不变）。"
        )
