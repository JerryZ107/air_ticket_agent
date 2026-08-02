#!/usr/bin/env python3
"""分析 eval/ques_batch_results.json 回复质量。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "ques_batch_results.json"

# 手册关键点（子串匹配，不区分部分标点）
RAG_EXPECT = {
    "R01": ["1", "23"],
    "R02": ["23"],
    "R03": ["75"],
    "R05": ["200", "30"],
    "R06": ["勿", "不要", "不可", "禁止", "请勿", "先退"],
    "R07": ["7", "14"],
    "R08": ["10%"],
    "R09": ["50", "600"],
    "R10": ["21"],
    "R11": ["98", "4", "16"],
    "R14": ["48", "45"],
    "R15": ["20"],
    "R16": ["48", "200"],
    "R17": ["400-800-9588", "complaint@"],
    "R20": ["100"],
    "R21": ["100"],
    "M06": ["23", "50"],
}

ZHANGSAN_IDS = {"T01", "T02", "M01", "M02", "M03", "M04", "M07", "W01", "W02"}
LISI_IDS = {"T04", "T05", "W03", "W05", "A04"}


def load_results(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def analyze(data: dict) -> str:
    lines: list[str] = []
    results = data.get("results", [])
    lines.append(f"## 批量结果概览")
    lines.append(f"- 总计: {data.get('total')} | HTTP 成功: {data.get('ok')} | 失败: {data.get('failed')}")
    lines.append(f"- 含写操作: {data.get('include_destructive')}")
    lines.append("")

    issues: list[str] = []
    passes: list[str] = []

    for row in results:
        qid = row.get("id", "")
        reply = (row.get("reply") or "").strip()
        user = row.get("user", "")
        ok = row.get("ok")
        if not ok:
            issues.append(f"**{qid}** HTTP 失败: {row.get('error', '')[:200]}")
            continue

        # RAG 关键词
        if qid in RAG_EXPECT:
            need = RAG_EXPECT[qid]
            hit = sum(1 for k in need if k in reply)
            if hit < len(need) and qid == "R06":
                # 至少要有禁止先退后订的语义
                if not re.search(r"先退|退.*再订|不要.*退", reply):
                    issues.append(f"**{qid}** RAG/ADR：未明确反对「先退后订」")
                else:
                    passes.append(f"{qid} RAG/ADR 通过")
            elif hit < max(1, len(need) - 1):
                issues.append(f"**{qid}** 手册要点可能缺失（期望含: {need}）")
            else:
                passes.append(f"{qid} RAG 要点通过")

        # 张三不应出现他人订单 XYZ789（代客/会话绑定）
        if qid in ZHANGSAN_IDS and user == "zhangsan" and "XYZ789" in reply:
            issues.append(f"**{qid}** 会话污染：zhangsan 回复出现 XYZ789")

        # lisi 不应泄露 ABC123 行程细节（可有「无法」类）
        if qid == "T04" and "ABC123" in reply and "无法" not in reply and "没有" not in reply:
            if "XYZ789" not in reply or "ABC123" in reply.split("XYZ789")[0]:
                issues.append(f"**T04** 越权：可能泄露或混淆 ABC123")

        # A03 lisi 代客
        if qid == "A03":
            if not any(k in reply for k in ("无权", "仅管理员", "不能", "无法代", "管理员")):
                issues.append(f"**A03** lisi 代客应被拒绝")

        # admin 列表应含两位旅客或用户名
        if qid == "A02":
            if "zhangsan" not in reply.lower() and "张三" not in reply:
                if "lisi" not in reply.lower() and "李四" not in reply:
                    issues.append(f"**A02** admin 全量列表宜标明旅客用户名")

        if qid == "A01" and "ABC123" not in reply:
            issues.append(f"**A01** 未看到 zhangsan 订单 ABC123")

        if qid == "A04" and "XYZ789" not in reply:
            issues.append(f"**A04** 未看到 lisi 订单 XYZ789")

        # M07 只查状态：不得出现「改签/转接」话术，也不得声称无工具
        if qid == "M07":
            if "改签" in reply and "转接" in reply:
                issues.append(f"**M07** 用户要求只查状态，仍出现改签/转接话术")
            if any(k in reply for k in ("不包含", "没有工具", "无法查询", "没有直接查询", "没有该工具")):
                issues.append(f"**M07** 声称无航班状态工具或拒绝查询")
            if "PA441" not in reply or ("延误" not in reply and "状态" not in reply):
                issues.append(f"**M07** 未给出 PA441 实际状态")

        # 内部转接旁白
        if "转接至分诊" in reply or "让我为您转接" in reply:
            issues.append(f"**{qid}** 回复含内部转接旁白（体验问题）")

    lines.append("## 自动检查通过（节选）")
    for p in passes[:15]:
        lines.append(f"- {p}")
    if len(passes) > 15:
        lines.append(f"- …共 {len(passes)} 条")
    lines.append("")
    lines.append("## 发现问题")
    if not issues:
        lines.append("- 无（按当前启发式规则）")
    else:
        for i in issues:
            lines.append(f"- {i}")

  # 耗时
    slow = sorted(
        [r for r in results if r.get("elapsed_ms", 0) > 25000],
        key=lambda x: -x.get("elapsed_ms", 0),
    )
    if slow:
        lines.append("")
        lines.append("## 慢查询 (>25s)")
        for r in slow[:8]:
            lines.append(f"- {r['id']}: {r.get('elapsed_ms')}ms")

    return "\n".join(lines)


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS
    if not path.exists():
        print(f"找不到结果文件: {path}")
        sys.exit(1)
    report = analyze(load_results(path))
    out = ROOT / "eval" / "ques_batch_analysis.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n已写入: {out}")


if __name__ == "__main__":
    main()
