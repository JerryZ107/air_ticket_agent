"""请求入口预处理（Binder）：在 Agent 运行前把会话身份与数据边界固化到 context。

设计原则：
- 登录用户：无条件注入全部订单快照 + 主订单。数据边界靠「注入」实现，
  而不是靠 prompt 要求模型「记得先查数据」——模型拿到的数据天然只有本人可见；
- admin 代客：从消息中确定性提取旅客用户名并预绑定，写操作工具自动以该旅客身份执行；
- 未登录演示：按城市关键词预选场景并注入行程，替代「让模型先调用工具填充」的 prompt。
"""

from __future__ import annotations

import json
import re

from airline.context import AirlineAgentContext
from airline.demo_data import apply_itinerary_defaults
from airline.hydrate import actor_from_state, apply_booking_row
from db.repository.bookings import booking_repo
from llm_config import API_KEY, BASE_URL, MODEL_FLASH

_CUSTOMER_RE = re.compile(
    r"(?:旅客|用户|客户|乘客)\s*([a-zA-Z][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
_HELP_VERB_RE = re.compile(r"(?:帮|代|给)\s*([a-zA-Z][a-zA-Z0-9_]{2,})", re.IGNORECASE)
_NAME_ORDER_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9_]{2,})\s*(?:的|名下)", re.IGNORECASE)
_FLIGHT_LIKE_RE = re.compile(r"^[A-Za-z]{1,4}\d{2,}$")

_ORDER_SIGNALS = (
    "订单", "查", "取消", "改签", "退票", "座位", "名下",
    "代", "帮", "给", "旅客", "用户", "客户", "乘客",
)

_CITY_SCENARIO_KEYWORDS = ("paris", "new york", "austin", "巴黎", "纽约", "奥斯汀")


def _is_flight_like(name: str) -> bool:
    """航班号（NY900/PA441/CA1234 等）不是用户名，防止误提取。"""
    return bool(_FLIGHT_LIKE_RE.fullmatch(name))


def extract_on_behalf_of_username(text: str) -> str | None:
    """规则提取代客/查询目标用户名：旅客X / 帮X / 代X / 给X / X的订单 / X名下。"""
    for pattern in (_CUSTOMER_RE, _HELP_VERB_RE, _NAME_ORDER_RE):
        m = pattern.search(text.strip())
        if m:
            name = m.group(1).strip().lower()
            if not _is_flight_like(name):
                return name
    return None


async def _llm_extract_target(user_text: str) -> str | None:
    """规则漏掉时的模型兜底：提取目标旅客用户名（仅 admin 且疑似订单语义时调用）。"""
    if not API_KEY or not any(k in user_text for k in _ORDER_SIGNALS):
        return None
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL.rstrip("/"))
    prompt = (
        "用户是管理员，正在处理航空订单事务。从消息中提取被操作或被查询的旅客用户名"
        "（如 lisi、zhangsan）。只输出一行 JSON：{\"username\":\"lisi\"}；"
        "若没有明确旅客用户名则输出 {\"username\":null}。"
        "注意：航班号（如 NY900、PA441）不是用户名。"
        f"\n消息：{user_text}"
    )
    try:
        resp = await client.chat.completions.create(
            model=MODEL_FLASH,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group(0) if match else raw)
        name = str(data.get("username") or "").strip().lower()
        return name if name and not _is_flight_like(name) else None
    except Exception:
        return None


def select_demo_scenario(text: str) -> str:
    """未登录演示路径：按城市关键词预选场景（替代 prompt 里的城市关键词指令）。"""
    low = text.lower()
    return "disrupted" if any(k in low for k in _CITY_SCENARIO_KEYWORDS) else "on_time"


def _snapshot(rows) -> list[dict[str, str]]:
    return [
        {
            "confirmation_no": r.confirmation_no,
            "flight_no": r.flight_no or "",
            "origin": r.origin or "",
            "destination": r.destination or "",
            "seat": r.seat,
            "status": r.status,
            "owner_username": r.owner_username or "",
        }
        for r in rows
    ]


async def hydrate_user_data(state: AirlineAgentContext) -> None:
    """登录用户：注入全部订单快照，并把第一条作为主订单写入上下文。"""
    actor = actor_from_state(state)
    if actor is None:
        return
    if state.user_role == "admin" and state.on_behalf_of_username:
        rows = await booking_repo.list_bookings_for_customer(
            actor, state.on_behalf_of_username
        )
    else:
        rows = await booking_repo.list_bookings_for_actor(actor)
    state.bookings = _snapshot(rows)
    if rows:
        apply_booking_row(state, rows[0])


async def preprocess_message(state: AirlineAgentContext, user_text: str) -> None:
    """Agent 运行前统一预处理（binder）：身份提取 -> 数据注入。"""
    # 1) admin 代客目标预提取（先于数据注入，决定按谁的数据加载）
    if state.user_role == "admin":
        extracted = extract_on_behalf_of_username(user_text)
        if not extracted:
            extracted = await _llm_extract_target(user_text)
        if extracted:
            state.on_behalf_of_username = extracted

    # 2) 登录用户：注入订单数据；未登录演示：按关键词注入演示行程
    if state.user_id:
        await hydrate_user_data(state)
    else:
        apply_itinerary_defaults(state, scenario_key=select_demo_scenario(user_text))
