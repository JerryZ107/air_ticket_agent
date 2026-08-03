"""Binder 预处理层：会话身份提取与数据注入（数据边界不依赖 prompt）。"""

import asyncio

from airline.context import AirlineAgentContext
from pipeline.binder import (
    extract_on_behalf_of_username,
    preprocess_message,
    select_demo_scenario,
)


def test_extract_on_behalf_of_username():
    assert extract_on_behalf_of_username("代旅客lisi取消订单") == "lisi"
    assert extract_on_behalf_of_username("旅客 ZhangSan 的订单") == "zhangsan"
    assert extract_on_behalf_of_username("查一下我的订单") is None
    assert extract_on_behalf_of_username("") is None


def test_select_demo_scenario():
    assert select_demo_scenario("从巴黎到奥斯汀的联程延误了") == "disrupted"
    assert select_demo_scenario("帮我订一张票") == "on_time"


def test_preprocess_injects_demo_scenario_without_db():
    """未登录演示路径：入口直接注入行程，不再依赖模型调用工具填充。"""
    state = AirlineAgentContext()
    asyncio.run(preprocess_message(state, "巴黎到纽约延误了，怎么办"))
    assert state.scenario == "disrupted"
    assert state.flight_number == "PA441"
    assert state.confirmation_number == "IR-D204"


def test_preprocess_hydrates_user_bookings(db_pool):
    """登录用户：入口无条件注入全部订单快照 + 主订单。"""
    from db.repository.auth import auth_repo

    row = asyncio.run(auth_repo.get_user_by_username("zhangsan"))
    state = AirlineAgentContext(
        user_id=str(row["id"]),
        username="zhangsan",
        user_role="user",
    )
    asyncio.run(preprocess_message(state, "展示下我最近的订单"))
    assert state.bookings
    assert state.bookings[0]["confirmation_no"] == "ABC123"
    assert state.confirmation_number == "ABC123"
    assert all(b["owner_username"] == "" for b in state.bookings)


def test_preprocess_binds_admin_on_behalf(db_pool):
    """admin 代客：目标旅客在入口被确定性提取，且只注入该旅客的数据。"""
    from db.repository.auth import auth_repo

    row = asyncio.run(auth_repo.get_user_by_username("admin"))
    state = AirlineAgentContext(
        user_id=str(row["id"]),
        username="admin",
        user_role="admin",
    )
    asyncio.run(preprocess_message(state, "代旅客lisi取消订单"))
    assert state.on_behalf_of_username == "lisi"
    assert state.bookings
    assert all(b["owner_username"] == "lisi" for b in state.bookings)
