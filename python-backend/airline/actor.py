"""Resolve actor from agent run context."""

from __future__ import annotations

from uuid import UUID

from agents import RunContextWrapper

from airline.context import AirlineAgentChatContext
from db.repository.bookings import Actor


def actor_from_run(context: RunContextWrapper[AirlineAgentChatContext]) -> Actor | None:
    st = context.context.state
    if not st.user_id:
        return None
    return Actor(id=UUID(st.user_id), role=st.user_role or "user")
