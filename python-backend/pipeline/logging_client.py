"""Wrap OpenAI client to persist every chat completion to obs.llm_calls."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from openai import AsyncOpenAI

from db.observability import obs_writer
from pipeline.request_context import get_request_context

_call_counters: dict[str, int] = {}


def _trace_key() -> str:
    try:
        return str(get_request_context().trace_id)
    except Exception:
        return "no-trace"


def _next_call_index() -> int:
    key = _trace_key()
    _call_counters[key] = _call_counters.get(key, 0) + 1
    return _call_counters[key] - 1


def _serialize_messages(messages: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages or []:
        if isinstance(m, dict):
            out.append(m)
        else:
            out.append(
                {
                    "role": getattr(m, "role", None),
                    "content": getattr(m, "content", None),
                }
            )
    return out


def _extract_response(resp: Any) -> tuple[str | None, str | None, dict[str, Any]]:
    """Return (content, thinking_content, raw_message_dict)."""
    try:
        choice = resp.choices[0]
        msg = choice.message
        content = getattr(msg, "content", None) or ""
        thinking = (
            getattr(msg, "reasoning_content", None)
            or getattr(msg, "thinking_content", None)
            or getattr(msg, "reasoning", None)
        )
        raw: dict[str, Any] = {}
        if hasattr(msg, "model_dump"):
            raw = msg.model_dump()
        elif hasattr(msg, "dict"):
            raw = msg.dict()
        return content, thinking, raw
    except Exception:
        return None, None, {}


def wrap_openai_client(client: AsyncOpenAI) -> AsyncOpenAI:
    """Monkey-patch chat.completions.create on the given client."""
    original = client.chat.completions.create

    async def logged_create(*args: Any, **kwargs: Any) -> Any:
        t0 = time.time()
        model = str(kwargs.get("model", ""))
        messages = _serialize_messages(kwargs.get("messages"))
        thinking_enabled = bool(kwargs.get("reasoning_effort") or kwargs.get("extra_body"))
        trace_id = None
        try:
            trace_id = get_request_context().trace_id
        except Exception:
            pass

        try:
            resp = await original(*args, **kwargs)
            latency = int((time.time() - t0) * 1000)
            content, thinking, raw_msg = _extract_response(resp)
            usage = getattr(resp, "usage", None)
            pt = getattr(usage, "prompt_tokens", None) if usage else None
            ct = getattr(usage, "completion_tokens", None) if usage else None
            if trace_id:
                # fire-and-forget：不阻塞响应路径；进程正常退出前
                # 未完成的任务可能丢失（可接受，日志写入是尽力而为）
                asyncio.create_task(
                    obs_writer.log_llm_call(
                        trace_id,
                        call_index=_next_call_index(),
                        model=model,
                        request_messages=messages,
                        response_content=content,
                        thinking_content=thinking,
                        raw_response={"message": raw_msg, "model": model},
                        thinking_enabled=thinking_enabled,
                        prompt_tokens=pt,
                        completion_tokens=ct,
                        latency_ms=latency,
                        status="ok",
                    )
                )
            return resp
        except Exception as exc:
            latency = int((time.time() - t0) * 1000)
            if trace_id:
                asyncio.create_task(
                    obs_writer.log_llm_call(
                        trace_id,
                        call_index=_next_call_index(),
                        model=model,
                        request_messages=messages,
                        thinking_enabled=thinking_enabled,
                        latency_ms=latency,
                        status="error",
                        error_message=str(exc),
                    )
                )
            raise

    client.chat.completions.create = logged_create  # type: ignore[method-assign]
    return client
