"""Context sliding window + optional summary compression."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from openai import AsyncOpenAI

from db.observability import obs_writer
from llm_config import API_KEY, BASE_URL, MODEL_FLASH
from pipeline.request_context import get_request_context

KEEP_RECENT = 10
TRIGGER_AT = 14


def _text(item: dict[str, Any]) -> str:
    c = item.get("content")
    if isinstance(c, str):
        return c
    return str(c)


async def compress_if_needed(
    input_items: list[Any],
    *,
    thread_id: str,
    user_id: str,
) -> list[Any]:
    """超过 TRIGGER_AT 条时，用 Flash 摘要旧消息并保留最近 KEEP_RECENT 条。"""
    if len(input_items) <= TRIGGER_AT:
        return input_items

    old = input_items[: -KEEP_RECENT]
    recent = input_items[-KEEP_RECENT:]
    transcript = "\n".join(f"{m.get('role', '?')}: {_text(m)}" for m in old if isinstance(m, dict))
    summary = transcript[:2000]
    if API_KEY and len(transcript) > 500:
        try:
            client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL.rstrip("/"))
            resp = await client.chat.completions.create(
                model=MODEL_FLASH,
                messages=[
                    {
                        "role": "user",
                        "content": f"用中文简要摘要以下客服对话（保留确认号、航班号、意图）：\n{transcript[:6000]}",
                    }
                ],
                temperature=0,
            )
            summary = resp.choices[0].message.content or summary
        except Exception:
            pass

    try:
        ctx = get_request_context()
        await obs_writer.log_chat_summary(
            ctx.trace_id,
            UUID(user_id),
            thread_id,
            summary,
            len(old),
            MODEL_FLASH,
        )
    except Exception:
        pass

    return [{"role": "system", "content": f"历史对话摘要：{summary}"}, *recent]
