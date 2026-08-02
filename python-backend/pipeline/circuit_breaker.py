"""Simple circuit breaker for LLM / agent runs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from db.observability import obs_writer
from pipeline.request_context import get_request_context


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    open_seconds: float = 60.0
    failures: int = 0
    opened_at: float = 0.0
    state: str = "closed"  # closed | open | half_open

    def allow(self) -> bool:
        if self.state == "open":
            if time.time() - self.opened_at >= self.open_seconds:
                self.state = "half_open"
                return True
            return False
        return True

    async def record_failure(self, detail: dict | None = None) -> None:
        self.failures += 1
        await self._event("failure_recorded", detail or {})
        if self.failures >= self.failure_threshold:
            self.state = "open"
            self.opened_at = time.time()
            await self._event("opened", {"failures": self.failures})

    async def record_success(self) -> None:
        self.failures = 0
        if self.state != "closed":
            await self._event("closed", {})
        self.state = "closed"

    async def _event(self, event_type: str, detail: dict) -> None:
        try:
            ctx = get_request_context()
            await obs_writer.log_circuit_breaker(ctx.trace_id, self.name, event_type, detail)
        except Exception:
            pass


agent_breaker = CircuitBreaker(name="agent_run")
