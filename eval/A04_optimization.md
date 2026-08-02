# A04 优化立项：管理员查旅客确认号

## 问题（A04）

- **题目**：admin —「帮我查旅客 lisi 的订单确认号是多少？」
- **期望**：`list_customer_bookings(customer_username=lisi)` → 确认号 **XYZ789**（及航班/状态）。
- **现状**：回复「无法处理该确认号」——模型把「lisi」或无关确认号送进 `get_booking_for_actor` 类工具，未走代查旅客订单。

## 根因

1. **路由**：问句含「确认号」命中 FAQ 关键词（`router.py`），或进 Agent 后误用「确认号」工具而非 `list_customer_bookings`。
2. **工具集**：代查仅在分诊 `list_customer_bookings`；模型可能调用 `get_trip_details`（查 admin 本人）或把旅客名当确认号。
3. **观测**：`/api/chat` 用户消息曾落在 `thread_id=pending`，`qa.py` 需结合 JSON 补全 user 行。

## 目标

| 项 | 标准 |
|----|------|
| A04 | 明确写出 lisi 的确认号 XYZ789（与 seed 一致） |
| 不误伤 | zhangsan 政策题「确认号会变吗」仍走 FAQ |
| 审计 | 代查仍走 `tool_facade.list_customer_bookings` → `obs.tool_calls` |

## 已实施改动

1. **`pipeline/admin_customer.py`**：`旅客/用户/客户 + 用户名` 解析 + `list_customer_bookings` 直连答复。
2. **`server.respond`**：admin 命中代查问法时 **短路返回**（同 FAQ 直连），不经过多 Agent。
3. **`router.py`**：在 FAQ「确认号」规则 **之前** 增加「查指定旅客订单/确认号」→ 分诊。
4. **`main.py`**：用户/助手消息写入 `obs.chat_messages` 时使用真实 `thread_id` + `trace_id`。

## 验收

```powershell
python scripts/run_ques_batch.py --id-prefix A04
python scripts/qa.py --id A04
```

回复应含 `XYZ789`；`obs.tool_calls` 应有 `list_customer_bookings`。

## 后续（可选）

- Adminer 查看 `obs.route_decisions` 是否仍误进 FAQ。
- 扩展问法：「李四的订单」→ 显示名映射用户名。
- ChatKit 路径同样落库 `chat_messages`。
