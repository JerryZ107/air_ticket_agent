"""意图路由规则：关键词快路径优先级（不依赖 LLM / API Key）。"""

import asyncio

from pipeline.router import classify_and_route


def _route(text: str):
    return asyncio.run(classify_and_route(text))


def test_flight_status_precedes_booking_keywords():
    """「查状态但不要改签」必须路由到航班信息专员，而非订票专员。"""
    d = _route("只问一句：航班PA441现在什么状态？不要帮我改签")
    assert d.intent == "flight_info"
    assert d.target_agent == "Flight Information Agent"


def test_faq_keyword_routes_to_faq():
    d = _route("行李额度是多少？")
    assert d.intent == "faq"
    assert d.target_agent == "FAQ Agent"


def test_my_orders_routes_to_triage():
    d = _route("展示下我最近的订单")
    assert d.target_agent == "Triage Agent"


def test_admin_customer_lookup_routes_to_triage():
    d = _route("帮我查旅客lisi的订单确认号是多少？")
    assert d.target_agent == "Triage Agent"
    assert d.confidence >= 0.9


def test_booking_intent():
    d = _route("帮我改签到CA1234")
    assert d.intent == "booking"


def test_flight_status_plain():
    d = _route("NY900现在什么状态？")
    assert d.intent == "flight_info"
