# 全链路 Trace 写入 PostgreSQL obs schema

每次用户请求生成 `trace_id` 并写入 `obs.traces`；span 树写入 `obs.trace_spans`。LLM 完整 `request_messages`、`response_content`、`thinking_content` 写入 `obs.llm_calls`（禁止仅存 summary）。Tool、RAG、对话、护栏、熔断、路由决策各有专用表。`obs.audit_log` 记录**所有**写操作（User 与 Admin），Admin 代客时填 `on_behalf_of_user_id`。B 阶段可将 `obs` 拆至独立物理库，表结构不变。
