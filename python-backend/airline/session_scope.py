"""Session-bound actor: tools only operate as the logged-in user."""

from __future__ import annotations

from agents import RunContextWrapper

from airline.actor import actor_from_run
from airline.context import AirlineAgentChatContext
from db.repository.bookings import Actor


def is_logged_in(context: RunContextWrapper[AirlineAgentChatContext]) -> bool:
    st = context.context.state
    return bool(st.user_id and st.username)


def is_admin_session(context: RunContextWrapper[AirlineAgentChatContext]) -> bool:
    return (context.context.state.user_role or "") == "admin"


def require_session_username(context: RunContextWrapper[AirlineAgentChatContext]) -> str:
    uname = (context.context.state.username or "").strip()
    if not uname:
        raise ValueError("未登录，无法执行该操作。")
    return uname


def require_session_actor(context: RunContextWrapper[AirlineAgentChatContext]) -> Actor:
    actor = actor_from_run(context)
    if actor is None:
        raise ValueError("未登录，无法执行该操作。")
    return actor


def normalize_on_behalf_of_username(
    context: RunContextWrapper[AirlineAgentChatContext],
    on_behalf_of_username: str | None,
) -> str | None:
    """非管理员不得代客；管理员可传旅客 username，空则仅表示管理员本人会话。"""
    if on_behalf_of_username is None or not str(on_behalf_of_username).strip():
        return None
    target = str(on_behalf_of_username).strip()
    if not is_admin_session(context):
        session = require_session_username(context)
        if target != session:
            raise PermissionError("无权代客操作其他账户。")
        return None
    return target
