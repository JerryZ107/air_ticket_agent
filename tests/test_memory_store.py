"""ChatKit 内存存储的会话隔离（跨用户不可见、列表按 owner 过滤）。"""

import asyncio
from datetime import datetime

import pytest
from chatkit.store import NotFoundError
from chatkit.types import ThreadMetadata

from memory_store import MemoryStore


class _FakeUser:
    def __init__(self, uid: str) -> None:
        self.id = uid


def _thread(seq: int = 0) -> ThreadMetadata:
    return ThreadMetadata(id=f"thr_{seq}", created_at=datetime.now())


def _save(store: MemoryStore, thread: ThreadMetadata, user: _FakeUser) -> None:
    asyncio.run(store.save_thread(thread, {"user": user}))


def test_cross_user_load_is_not_found():
    store = MemoryStore()
    a, b = _FakeUser("a"), _FakeUser("b")
    t = _thread(0)
    _save(store, t, a)
    with pytest.raises(NotFoundError):
        asyncio.run(store.load_thread(t.id, {"user": b}))


def test_owner_can_load():
    store = MemoryStore()
    a = _FakeUser("a")
    t = _thread(0)
    _save(store, t, a)
    assert asyncio.run(store.load_thread(t.id, {"user": a})).id == t.id


def test_thread_list_filtered_by_owner():
    store = MemoryStore()
    a, b = _FakeUser("a"), _FakeUser("b")
    ta, tb = _thread(0), _thread(1)
    _save(store, ta, a)
    _save(store, tb, b)
    page = asyncio.run(store.load_threads(10, None, "desc", {"user": a}))
    assert [t.id for t in page.data] == [ta.id]


def test_anonymous_internal_call_allowed():
    store = MemoryStore()
    a = _FakeUser("a")
    t = _thread(0)
    _save(store, t, a)
    assert asyncio.run(store.load_thread(t.id, {})).id == t.id
