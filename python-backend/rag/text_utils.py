"""Chinese / mixed question tokenization for retrieval."""

from __future__ import annotations

import re


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
