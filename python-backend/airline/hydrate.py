"""Load booking facts from PostgreSQL into agent context."""

from __future__ import annotations

from uuid import UUID

from db.repository.bookings import Actor, BookingRow, booking_repo

from .context import AirlineAgentContext


def actor_from_state(state: AirlineAgentContext) -> Actor | None:
    if not state.user_id:
        return None
    return Actor(id=UUID(state.user_id), role=state.user_role or "user")


def apply_booking_row(state: AirlineAgentContext, row: BookingRow) -> None:
    state.confirmation_number = row.confirmation_no
    state.flight_number = row.flight_no
    state.seat_number = row.seat
    state.origin = row.origin
    state.destination = row.destination


async def hydrate_first_booking(state: AirlineAgentContext) -> bool:
    """Fill context from the user's first active booking. Returns True if hydrated."""
    actor = actor_from_state(state)
    if actor is None:
        return False
    rows = await booking_repo.list_bookings_for_actor(actor)
    if not rows:
        return False
    apply_booking_row(state, rows[0])
    return True
