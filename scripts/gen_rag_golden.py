#!/usr/bin/env python3
"""Generate eval/rag_golden.jsonl from docs/manual section titles (50 paraphrases)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "eval" / "rag_golden.jsonl"

SOURCE_BY_CATEGORY = {
    "baggage": "01-baggage.md",
    "rebook": "02-rebooking.md",
    "refund": "03-cancellation.md",
    "compensation": "04-delay-compensation.md",
    "seat": "05-seat-selection.md",
    "service": "06-wifi-amenities.md",
}

CASES: list[dict] = [
    # 行李
    {"question": "登机行李重量限制是多少", "must_contain": "23", "category": "baggage"},
    {"question": "随身行李尺寸要求", "must_contain": "56", "category": "baggage"},
    {"question": "经济舱托运行李额度", "must_contain": "经济舱", "category": "baggage"},
    {"question": "托运行李超重怎么收费", "must_contain": "75", "category": "baggage"},
    {"question": "行李延误或丢失怎么办", "must_contain": "索赔", "category": "baggage"},
    {"question": "可以多带一件登机行李吗", "must_contain": "一件", "category": "baggage"},
    {"question": "超重行李费多少钱", "must_contain": "美元", "category": "baggage"},
    {"question": "23公斤是登机还是托运", "must_contain": "登机", "category": "baggage"},
    # 改签
    {"question": "改签后确认号会变吗", "must_contain": "确认号", "category": "rebook"},
    {"question": "同一确认号上改签规则", "must_contain": "不变", "category": "rebook"},
    {"question": "能不能先退票再重新订票", "must_contain": "请勿", "category": "rebook"},
    {"question": "换一个航班怎么办理", "must_contain": "改签", "category": "rebook"},
    {"question": "改签失败原订单会怎样", "must_contain": "保持不变", "category": "rebook"},
    {"question": "改签要不要补差价", "must_contain": "差价", "category": "rebook"},
    {"question": "改签前需要锁定座位吗", "must_contain": "锁定", "category": "rebook"},
    {"question": "说换一个航班是改签吗", "must_contain": "改签", "category": "rebook"},
    {"question": "确认号不变是什么意思", "must_contain": "确认号", "category": "rebook"},
    # 退票
    {"question": "退票多久到账", "must_contain": "7", "category": "refund"},
    {"question": "退票后订单状态", "must_contain": "取消", "category": "refund"},
    {"question": "退款原路退回要几天", "must_contain": "工作日", "category": "refund"},
    {"question": "取消订票座位会释放吗", "must_contain": "释放", "category": "refund"},
    {"question": "退票政策是什么", "must_contain": "退票", "category": "refund"},
    {"question": "申请退款时间", "must_contain": "14", "category": "refund"},
    {"question": "退票后还能坐吗", "must_contain": "取消", "category": "refund"},
    {"question": "怎么办理退票", "must_contain": "退款", "category": "refund"},
    # 延误补偿
    {"question": "航班延误超过三小时有什么补偿", "must_contain": "酒店", "category": "compensation"},
    {"question": "长时间延误提供餐券吗", "must_contain": "餐券", "category": "compensation"},
    {"question": "错过后续航班能补偿吗", "must_contain": "延误", "category": "compensation"},
    {"question": "里程积分补偿怎么申请", "must_contain": "积分", "category": "compensation"},
    {"question": "延误补偿要留收据吗", "must_contain": "收据", "category": "compensation"},
    {"question": "地面交通延误有补贴吗", "must_contain": "交通", "category": "compensation"},
    {"question": "超过3小时延误政策", "must_contain": "3", "category": "compensation"},
    {"question": "创建补偿案例", "must_contain": "补偿", "category": "compensation"},
    # 选座
    {"question": "安全出口在第几排", "must_contain": "16", "category": "seat"},
    {"question": "这架飞机有多少座位", "must_contain": "120", "category": "seat"},
    {"question": "商务舱有多少座", "must_contain": "22", "category": "seat"},
    {"question": "经济舱座位数", "must_contain": "98", "category": "seat"},
    {"question": "第4排是安全出口吗", "must_contain": "4", "category": "seat"},
    {"question": "选座一共几排安全出口", "must_contain": "出口", "category": "seat"},
    {"question": "机型座位布局", "must_contain": "商务舱", "category": "seat"},
    {"question": "安全出口排位置", "must_contain": "排", "category": "seat"},
    # 机上服务
    {"question": "机上 WiFi 怎么连", "must_contain": "Wifi", "category": "service"},
    {"question": "有免费无线网络吗", "must_contain": "Wi-Fi", "category": "service"},
    {"question": "飞机上网连接名称", "must_contain": "Airline", "category": "service"},
    {"question": "机上能上网吗", "must_contain": "Wi-Fi", "category": "service"},
    {"question": "怎么连接航空公司wifi", "must_contain": "连接", "category": "service"},
    {"question": "机上网络免费吗", "must_contain": "免费", "category": "service"},
    {"question": "托运和登机行李区别", "must_contain": "托运", "category": "baggage"},
    {"question": "改签和退票有什么区别", "must_contain": "改签", "category": "rebook"},
    {"question": "延误多久算长时间", "must_contain": "3", "category": "compensation"},
]

for c in CASES:
    c["expected_source"] = SOURCE_BY_CATEGORY[c["category"]]

assert len(CASES) == 50, len(CASES)

OUT.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in CASES) + "\n", encoding="utf-8")
print(f"Wrote {len(CASES)} cases to {OUT}")
