"""管理员全库最近订单直答：复用 Binder 注入的订单快照，绕过 Agent 与工具。"""

from airline.context import AirlineAgentContext
from pipeline.admin_recent import format_admin_recent_orders, is_admin_recent_orders


def test_admin_recent_orders_matching():
    assert is_admin_recent_orders("列出最近的订单")
    assert is_admin_recent_orders("查一下全库最近订单")
    assert is_admin_recent_orders("全部订单列出来")
    assert is_admin_recent_orders("订单列表")
    assert is_admin_recent_orders("列出系统里最近订单，并说明每条订单属于哪位旅客用户名")
    assert not is_admin_recent_orders("代旅客lisi取消订单")
    assert not is_admin_recent_orders("查旅客lisi的订单")
    assert not is_admin_recent_orders("我最近的订单")
    assert not is_admin_recent_orders("改签到CA1234")
    assert not is_admin_recent_orders("")


def test_format_admin_recent_orders_uses_injected_snapshot():
    state = AirlineAgentContext(
        bookings=[
            {
                "confirmation_no": "XYZ789",
                "flight_no": "CA123",
                "origin": "北京",
                "destination": "上海",
                "seat": "12A",
                "status": "已确认",
                "owner_username": "lisi",
            }
        ]
    )
    out = format_admin_recent_orders(state)
    assert out is not None
    assert "旅客lisi" in out
    assert "XYZ789" in out
    assert "CA123" in out


def test_format_admin_recent_orders_empty_returns_none():
    assert format_admin_recent_orders(AirlineAgentContext()) is None
