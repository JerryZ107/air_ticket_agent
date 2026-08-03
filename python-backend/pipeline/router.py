"""Intent classification and model/agent routing (Flash)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import AsyncOpenAI

from db.observability import obs_writer
from llm_config import API_KEY, BASE_URL, MODEL_FLASH, MODEL_PRO
from pipeline.request_context import get_request_context

INTENTS = ("faq", "flight_info", "booking", "seat", "compensation", "chitchat", "unknown")


@dataclass
class RouteDecision:
    intent: str
    confidence: float
    target_agent: str
    model_selected: str
    clarify_question: str | None = None


_AGENT_MAP = {
    "faq": "FAQ Agent",
    "flight_info": "Flight Information Agent",
    "booking": "Booking and Cancellation Agent",
    "seat": "Seat and Special Services Agent",
    "compensation": "Refunds and Compensation Agent",
    "chitchat": "Triage Agent",
    "unknown": "Triage Agent",
}


async def classify_and_route(user_text: str) -> RouteDecision:
    """Flash 意图分类；低置信度时生成追问。"""
    text = user_text.strip()
    if not text:
        return RouteDecision("unknown", 0.0, "Triage Agent", MODEL_FLASH, "请描述您的航班或订票问题。")

    # 查本人订单（须在「订票」关键词规则之前，避免误路由）
    if any(
        k in text
        for k in (
            "我的订单",
            "查询订单",
            "查订单",
            "订单列表",
            "有没有订票",
            "有订票吗",
            "是否有订票",
            "有没有订单",
            "查询下我的",
            "查看一下我",
            "我最近的订单",
            "最近的订单",
            "展示下我",
            "我的行程",
        )
    ):
        d = RouteDecision("chitchat", 0.93, "Triage Agent", MODEL_FLASH)
        await _log_route(d)
        return d

    # 查指定旅客订单/确认号（须在 FAQ「确认号」关键词之前）
    if re.search(r"(旅客|用户|客户|乘客)\s*[a-zA-Z]", text):
        if any(k in text for k in ("确认号", "订单", "查", "查询", "列表", "名下")):
            d = RouteDecision("chitchat", 0.95, "Triage Agent", MODEL_FLASH)
            await _log_route(d)
            return d

    # 规则快速路径（省 token）— 政策类优先 FAQ，避免订票专员泛化回答
    faq_keywords = (
        "行李", "退票政策", "改签规则", "补偿", "手册", "额度", "改期费", "退票费",
        "先退", "后订", "值机", "登机口", "安全出口", "A320", "机型", "充电宝",
        "液态", "Wi-Fi", "WIFI", "SSID", "UM", "无成人", "海关", "申报", "电话",
        "邮箱", "确认号", "退款", "工作日",
    )
    if any(k in text for k in faq_keywords):
        d = RouteDecision("faq", 0.92, _AGENT_MAP["faq"], MODEL_FLASH)
        await _log_route(d)
        return d
    # 航班状态查询先于「取消/改签」关键词，避免「查状态但不要改签」被误路由到订票专员
    if any(k in text for k in ("航班", "延误", "登机", "PA", "NY")) and "状态" in text:
        d = RouteDecision("flight_info", 0.85, _AGENT_MAP["flight_info"], MODEL_FLASH)
        await _log_route(d)
        return d
    if any(k in text for k in ("取消", "退票", "改签", "预订")) or (
        "订票" in text and "订单" not in text
    ):
        # 纯政策问法仍走 FAQ
        if any(k in text for k in ("政策", "规则", "多少", "多久", "能不能", "可以吗", "是否")):
            d = RouteDecision("faq", 0.9, _AGENT_MAP["faq"], MODEL_FLASH)
            await _log_route(d)
            return d
        d = RouteDecision("booking", 0.88, _AGENT_MAP["booking"], MODEL_PRO)
        await _log_route(d)
        return d

    if not API_KEY:
        d = RouteDecision("unknown", 0.5, "Triage Agent", MODEL_FLASH)
        await _log_route(d)
        return d

    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL.rstrip("/"))
    prompt = (
        "你是意图分类器。根据用户消息输出 JSON："
        '{"intent":"faq|flight_info|booking|seat|compensation|chitchat|unknown",'
        '"confidence":0-1,"clarify_question":null或追问中文}'
        f"\n用户：{text}"
    )
    try:
        resp = await client.chat.completions.create(
            model=MODEL_FLASH,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = resp.choices[0].message.content or "{}"
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group(0) if match else raw)
        intent = data.get("intent", "unknown")
        if intent not in INTENTS:
            intent = "unknown"
        conf = float(data.get("confidence", 0.5))
        clarify = data.get("clarify_question")
        model = MODEL_PRO if intent in ("booking", "seat") else MODEL_FLASH
        if conf < 0.7:
            clarify = clarify or "请问您是要查询航班、办理退改签，还是咨询订票政策？"
        d = RouteDecision(intent, conf, _AGENT_MAP.get(intent, "Triage Agent"), model, clarify)
        await _log_route(d)
        return d
    except Exception:
        d = RouteDecision("unknown", 0.4, "Triage Agent", MODEL_FLASH)
        await _log_route(d)
        return d


async def _log_route(d: RouteDecision) -> None:
    try:
        ctx = get_request_context()
        await obs_writer.log_route_decision(
            ctx.trace_id,
            d.intent,
            d.confidence,
            d.target_agent,
            d.model_selected,
            d.clarify_question,
        )
    except Exception:
        pass
