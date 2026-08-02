"""Request-scoped trace and actor context."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass
class RequestContext:
    trace_id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    username: str | None = None
    role: str = "user"
    thread_id: str | None = None
    chat_sequence: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def next_chat_sequence(self) -> int:
        self.chat_sequence += 1
        return self.chat_sequence


_request_ctx: ContextVar[RequestContext | None] = ContextVar("request_ctx", default=None)


def get_request_context() -> RequestContext:
    ctx = _request_ctx.get()
    if ctx is None:
        ctx = RequestContext()
        _request_ctx.set(ctx)
    return ctx


def set_request_context(ctx: RequestContext) -> None:
    _request_ctx.set(ctx)


def clear_request_context() -> None:
    _request_ctx.set(None)
