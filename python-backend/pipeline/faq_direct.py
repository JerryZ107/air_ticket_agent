"""FAQ 直连：严格基于 faq_lookup 结果生成客户回复。"""

from __future__ import annotations

import re

from openai import AsyncOpenAI

from llm_config import API_KEY, BASE_URL, MODEL_FLASH
from rag.retriever import NOT_FOUND_ANSWER
from services import tool_facade as api


async def answer_from_manual(question: str) -> str:
    """先 RAG 检索，再让模型仅用检索文本组织中文答复。"""
    rag = await api.faq_lookup(question.strip())
    if NOT_FOUND_ANSWER[:12] in rag or "手册未收录" in rag:
        return (
            "抱歉，我在订票手册中没有检索到与您问题直接相关的条款，"
            "目前无法确认答案。建议您换个说法或联系人工客服（400-800-9588）。"
        )

    if not API_KEY:
        return _strip_rag_for_display(rag)

    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL.rstrip("/"))
    prompt = (
        "你是航空公司客服。下面「手册摘录」是唯一依据。"
        "请用简体中文简洁回答客户问题；数字、规则必须与摘录完全一致，不得补充行业常识。"
        "若摘录不足以回答，只说「手册中暂无相关规定，无法确认」。"
        f"\n\n客户问题：{question}\n\n手册摘录：\n{rag[:6000]}"
    )
    try:
        resp = await client.chat.completions.create(
            model=MODEL_FLASH,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception:
        pass
    return _strip_rag_for_display(rag)


def _strip_rag_for_display(rag: str) -> str:
    body = re.sub(r"^【[^】]+】[^\n]*\n+", "", rag).strip()
    return f"根据订票手册：\n{body[:2500]}"
