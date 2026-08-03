"""数据库集成：登录、越权防护、admin 代查、Saga 非破坏性改签。"""

import asyncio

import pytest

from db.repository.auth import auth_repo
from db.repository.bookings import Actor, booking_repo


async def _actor(username: str) -> Actor:
    row = await auth_repo.get_user_by_username(username)
    assert row is not None, f"seed user missing: {username}"
    return Actor(id=row["id"], role=row["role"])


def test_login_verifies_seed_user(db_pool):
    user = asyncio.run(auth_repo.verify_login("zhangsan", "demo123"))
    assert user is not None
    assert user.role == "user"
    assert asyncio.run(auth_repo.verify_login("zhangsan", "wrong-password")) is None


def test_user_cannot_access_other_booking(db_pool):
    zhangsan = asyncio.run(_actor("zhangsan"))
    lisi = asyncio.run(_actor("lisi"))
    own = asyncio.run(booking_repo.get_booking_for_actor(zhangsan, "ABC123"))
    assert own is not None and own.confirmation_no == "ABC123"
    with pytest.raises(PermissionError):
        asyncio.run(booking_repo.get_booking_for_actor(lisi, "ABC123"))


def test_admin_can_list_customer_bookings(db_pool):
    admin = asyncio.run(_actor("admin"))
    rows = asyncio.run(booking_repo.list_bookings_for_customer(admin, "zhangsan"))
    assert any(r.confirmation_no == "ABC123" for r in rows)


def test_non_admin_cannot_list_customer(db_pool):
    lisi = asyncio.run(_actor("lisi"))
    with pytest.raises(PermissionError):
        asyncio.run(booking_repo.list_bookings_for_customer(lisi, "zhangsan"))


def test_saga_rebook_to_same_flight_is_non_destructive(db_pool):
    from db.repository.saga import RebookingSaga

    zhangsan = asyncio.run(_actor("zhangsan"))
    before = asyncio.run(booking_repo.get_booking_for_actor(zhangsan, "ABC123"))
    assert before is not None
    msg = asyncio.run(
        RebookingSaga().run(zhangsan, "ABC123", "NY900", before.seat)
    )
    after = asyncio.run(booking_repo.get_booking_for_actor(zhangsan, "ABC123"))
    assert after is not None
    assert "ABC123" in msg and "确认号" in msg
    assert after.flight_id == before.flight_id
    assert after.seat == before.seat
    assert after.status == before.status
