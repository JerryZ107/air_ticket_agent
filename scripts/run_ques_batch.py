#!/usr/bin/env python3
"""从 ques.md 读取问题 JSON，批量调用 /api/chat。"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
QUES_MD = ROOT / "ques.md"
DEFAULT_BASE = "http://127.0.0.1:8001"
DEFAULT_PASSWORD = "demo123"


def load_questions(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"<!-- QUESTIONS_JSON -->\s*```json\s*(.*?)\s*```", text, re.DOTALL)
    if not m:
        raise SystemExit(f"未在 {path} 中找到 QUESTIONS_JSON 块")
    return json.loads(m.group(1))


def run_batch(
    base_url: str,
    password: str,
    include_destructive: bool,
    timeout_s: float,
    out_path: Path,
    id_prefix: str | None = None,
) -> None:
    questions = load_questions(QUES_MD)
    if id_prefix:
        questions = [q for q in questions if str(q.get("id", "")).startswith(id_prefix)]
    if not include_destructive:
        questions = [q for q in questions if not q.get("destructive")]

    results: list[dict] = []
    started = datetime.now(timezone.utc).isoformat()

    with httpx.Client(base_url=base_url, timeout=timeout_s) as client:
        tokens: dict[str, str] = {}

        def login(username: str) -> str:
            if username in tokens:
                return tokens[username]
            r = client.post(
                "/api/auth/login",
                json={"username": username, "password": password},
            )
            if r.status_code != 200:
                raise RuntimeError(f"login {username} failed: {r.status_code} {r.text}")
            # 关键：清除登录响应设置的 session cookie，否则后续请求
            # 会以"最后登录用户"的身份执行（后端优先取 cookie），
            # 造成不同用例间的会话污染（如 zhangsan 用例看到 lisi 的订单）。
            client.cookies.clear()
            token = r.json()["token"]
            tokens[username] = token
            return token

        for i, q in enumerate(questions, 1):
            qid = q.get("id", f"Q{i}")
            user = q["user"]
            text = q["text"]
            print(f"[{i}/{len(questions)}] {qid} ({user}) …", flush=True)
            t0 = time.perf_counter()
            row: dict = {
                "id": qid,
                "user": user,
                "category": q.get("category"),
                "source": q.get("source"),
                "destructive": q.get("destructive", False),
                "question": text,
            }
            try:
                token = login(user)
                r = client.post(
                    "/api/chat",
                    json={"message": text},
                    headers={"Authorization": f"Bearer {token}"},
                )
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                row["status_code"] = r.status_code
                row["elapsed_ms"] = elapsed_ms
                if r.status_code == 200:
                    data = r.json()
                    row["thread_id"] = data.get("thread_id")
                    row["reply"] = data.get("reply")
                    row["ok"] = True
                else:
                    row["ok"] = False
                    row["error"] = r.text[:2000]
            except Exception as exc:
                row["ok"] = False
                row["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
                row["error"] = str(exc)
            results.append(row)

    summary = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "total": len(results),
        "ok": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "include_destructive": include_destructive,
        "results": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成: ok={summary['ok']} failed={summary['failed']}")
    print(f"结果: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="批量跑 ques.md 中的 /api/chat 测试")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--include-destructive", action="store_true")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "eval" / "ques_batch_results.json",
    )
    parser.add_argument("--id-prefix", default=None, help="仅跑 id 前缀，如 R")
    args = parser.parse_args()
    run_batch(
        args.base_url,
        args.password,
        args.include_destructive,
        args.timeout,
        args.out,
        args.id_prefix,
    )


if __name__ == "__main__":
    main()
