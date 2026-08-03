"""Chinese / mixed question tokenization for retrieval."""

from __future__ import annotations

import re


def split_sub_questions(question: str) -> list[str]:
    """复合问题拆分为子问题（按问号/句号/分号切分）。

    例如「行李额度是多少？如果延误3小时以上有什么餐券？」拆为两个子问题
    分别检索、合并证据，避免只命中一个主题导致漏答。单一问题返回原样。
    """
    parts = [p.strip() for p in re.split(r"[？?。;；]+", question) if p.strip()]
    return parts or [question.strip()]


def question_terms(question: str, *, max_terms: int = 16) -> list[str]:
    q = re.sub(r"\s+", "", question.strip())
    terms: list[str] = []
    for seg in re.findall(r"[\u4e00-\u9fff]+", q):
        if 2 <= len(seg) <= 4:
            terms.append(seg)
        else:
            for i in range(len(seg) - 1):
                terms.append(seg[i : i + 2])
            terms.append(seg[:4])
    terms.extend(re.findall(r"[A-Za-z0-9]{2,}", question))
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
        if len(out) >= max_terms:
            break
    if not out and q:
        out = [q[:20]]
    return out
