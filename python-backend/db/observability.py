"""Persist traces, LLM calls, tools, audit to obs schema."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from db.pool import get_pool


class ObservabilityWriter:
    async def start_trace(
        self,
        trace_id: UUID,
        user_id: UUID,
        thread_id: str | None,
        request_path: str | None = None,
    ) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.traces (id, user_id, thread_id, request_path, status)
                VALUES ($1, $2, $3, $4, 'running')
                """,
                trace_id,
                user_id,
                thread_id,
                request_path,
            )

    async def end_trace(
        self,
        trace_id: UUID,
        status: str = "ok",
        error_message: str | None = None,
    ) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE obs.traces
                SET status = $2, ended_at = now(), error_message = $3
                WHERE id = $1
                """,
                trace_id,
                status,
                error_message,
            )

    async def add_span(
        self,
        trace_id: UUID,
        span_name: str,
        span_type: str,
        *,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        status: str = "ok",
        agent_name: str | None = None,
        model: str | None = None,
        latency_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        from uuid import uuid4

        sid = span_id or uuid4()
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.trace_spans (
                    id, trace_id, parent_span_id, span_name, span_type,
                    status, agent_name, model, latency_ms, metadata, ended_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, now())
                """,
                sid,
                trace_id,
                parent_span_id,
                span_name,
                span_type,
                status,
                agent_name,
                model,
                latency_ms,
                json.dumps(metadata or {}),
            )
        return sid

    async def log_llm_call(
        self,
        trace_id: UUID,
        *,
        span_id: UUID | None = None,
        call_index: int = 0,
        model: str,
        request_messages: list[dict[str, Any]],
        response_content: str | None = None,
        thinking_content: str | None = None,
        raw_response: dict[str, Any] | None = None,
        thinking_enabled: bool = False,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        thinking_tokens: int | None = None,
        latency_ms: int | None = None,
        status: str = "ok",
        error_message: str | None = None,
    ) -> None:
        pool = get_pool()
        total = None
        if prompt_tokens is not None or completion_tokens is not None:
            total = (prompt_tokens or 0) + (completion_tokens or 0) + (thinking_tokens or 0)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.llm_calls (
                    trace_id, span_id, call_index, model, thinking_enabled,
                    request_messages, response_content, thinking_content, raw_response,
                    prompt_tokens, completion_tokens, thinking_tokens, total_tokens,
                    latency_ms, status, error_message
                )
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9::jsonb,$10,$11,$12,$13,$14,$15,$16)
                """,
                trace_id,
                span_id,
                call_index,
                model,
                thinking_enabled,
                json.dumps(request_messages),
                response_content,
                thinking_content,
                json.dumps(raw_response) if raw_response else None,
                prompt_tokens,
                completion_tokens,
                thinking_tokens,
                total,
                latency_ms,
                status,
                error_message,
            )

    async def log_tool_call(
        self,
        trace_id: UUID,
        tool_name: str,
        input_json: dict[str, Any],
        output_json: dict[str, Any] | None,
        *,
        span_id: UUID | None = None,
        status: str = "ok",
        latency_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.tool_calls (
                    trace_id, span_id, tool_name, input_json, output_json,
                    status, latency_ms, error_message
                )
                VALUES ($1,$2,$3,$4::jsonb,$5::jsonb,$6,$7,$8)
                """,
                trace_id,
                span_id,
                tool_name,
                json.dumps(input_json),
                json.dumps(output_json) if output_json else None,
                status,
                latency_ms,
                error_message,
            )

    async def log_chat_message(
        self,
        user_id: UUID,
        thread_id: str,
        sequence_no: int,
        role: str,
        content: str,
        *,
        trace_id: UUID | None = None,
        thinking_content: str | None = None,
    ) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.chat_messages (
                    trace_id, user_id, thread_id, sequence_no, role, content, thinking_content
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (thread_id, sequence_no) DO UPDATE SET
                    content = EXCLUDED.content,
                    thinking_content = EXCLUDED.thinking_content
                """,
                trace_id,
                user_id,
                thread_id,
                sequence_no,
                role,
                content,
                thinking_content,
            )

    async def log_audit(
        self,
        actor_id: UUID,
        actor_role: str,
        action: str,
        target_type: str,
        target_id: UUID | None,
        *,
        trace_id: UUID | None = None,
        on_behalf_of_user_id: UUID | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
    ) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.audit_log (
                    trace_id, actor_id, actor_role, action, target_type, target_id,
                    on_behalf_of_user_id, before_state, after_state
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb)
                """,
                trace_id,
                actor_id,
                actor_role,
                action,
                target_type,
                target_id,
                on_behalf_of_user_id,
                json.dumps(before_state) if before_state else None,
                json.dumps(after_state) if after_state else None,
            )

    async def log_guardrail(
        self,
        trace_id: UUID,
        guardrail_name: str,
        input_text: str,
        passed: bool,
        reasoning: str = "",
        model: str | None = None,
        span_id: UUID | None = None,
    ) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.guardrail_checks (
                    trace_id, span_id, guardrail_name, input_text, passed, reasoning, model
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                """,
                trace_id,
                span_id,
                guardrail_name,
                input_text,
                passed,
                reasoning,
                model,
            )

    async def log_route_decision(
        self,
        trace_id: UUID,
        intent: str | None,
        confidence: float | None,
        target_agent: str | None,
        model_selected: str | None,
        clarify_question: str | None = None,
    ) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.route_decisions (
                    trace_id, intent, confidence, target_agent, model_selected, clarify_question
                )
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                trace_id,
                intent,
                confidence,
                target_agent,
                model_selected,
                clarify_question,
            )

    async def log_chat_summary(
        self,
        trace_id: UUID | None,
        user_id: UUID,
        thread_id: str,
        summary_text: str,
        compressed_count: int,
        model: str | None = None,
    ) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.chat_summaries (
                    trace_id, user_id, thread_id, summary_text,
                    compressed_from_seq, compressed_to_seq, model
                )
                VALUES ($1,$2,$3,$4,0,$5,$6)
                """,
                trace_id,
                user_id,
                thread_id,
                summary_text,
                compressed_count,
                model,
            )

    async def log_circuit_breaker(
        self,
        trace_id: UUID | None,
        breaker_name: str,
        event_type: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.circuit_breaker_events (trace_id, breaker_name, event_type, detail)
                VALUES ($1,$2,$3,$4::jsonb)
                """,
                trace_id,
                breaker_name,
                event_type,
                json.dumps(detail or {}),
            )


obs_writer = ObservabilityWriter()
