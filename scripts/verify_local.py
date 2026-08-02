#!/usr/bin/env python3
"""Quick local smoke test against http://127.0.0.1:8001."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"


def req(method: str, path: str, body: dict | None = None, cookie: str | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if cookie:
        headers["Cookie"] = f"session_token={cookie}"
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> int:
    ok = True
    code, health = req("GET", "/health")
    print(f"[{'OK' if code == 200 else 'FAIL'}] GET /health -> {code} {health}")
    ok &= code == 200

    code, _ = req("POST", "/api/chat", {"message": "test"})
    print(f"[{'OK' if code == 401 else 'FAIL'}] POST /api/chat (no auth) -> {code}")
    ok &= code == 401

    code, login = req("POST", "/api/auth/login", {"username": "zhangsan", "password": "demo123"})
    token = login.get("token") if isinstance(login, dict) else None
    print(f"[{'OK' if code == 200 and token else 'FAIL'}] POST /api/auth/login -> {code} user={login.get('username') if isinstance(login, dict) else login}")
    ok &= code == 200 and bool(token)

    code, me = req("GET", "/api/auth/me", cookie=token)
    print(f"[{'OK' if code == 200 else 'FAIL'}] GET /api/auth/me -> {me}")
    ok &= code == 200

    code, chat = req(
        "POST",
        "/api/chat",
        {"message": "退票政策是什么", "thread_id": "smoke-faq"},
        cookie=token,
    )
    reply = chat.get("reply", "") if isinstance(chat, dict) else ""
    print(f"[{'OK' if code == 200 and len(reply) > 20 else 'FAIL'}] POST /api/chat (FAQ) -> {code} reply_len={len(reply)}")
    if reply:
        print(f"  preview: {reply[:120]}...")
    ok &= code == 200 and len(reply) > 20

    code, clarify = req(
        "POST",
        "/api/chat",
        {"message": "嗯", "thread_id": "smoke-clarify"},
        cookie=token,
    )
    cr = clarify.get("reply", "") if isinstance(clarify, dict) else ""
    print(f"[{'OK' if code == 200 and cr else 'FAIL'}] POST /api/chat (clarify) -> {code} reply={cr[:80]}")
    ok &= code == 200 and bool(cr)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
