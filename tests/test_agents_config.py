"""Agent 配置：行为域 Agent 同时具备知识工具与操作工具（知识/操作模糊边界在 Agent 内部解决）。"""

from airline.agents import booking_cancellation_agent


def _tool_names(agent) -> set[str]:
    return {getattr(t, "name", "") for t in agent.tools}


def test_booking_agent_has_faq_tool():
    """订票改签专员必须能查手册，政策/流程类问题不再依赖路由区分。"""
    assert "faq_lookup_tool" in _tool_names(booking_cancellation_agent)


def test_booking_agent_has_action_tools():
    """同时保留订/退/改等操作工具。"""
    names = _tool_names(booking_cancellation_agent)
    assert {"cancel_flight", "book_new_flight", "rebook_flight"} <= names
