# 航班订票助理 Agent — Grilling 会话记录

> 基于 `/grill-with-docs` 技能，在动手实现前澄清领域模型与架构决策。
> 会话规则：**一次只问一个问题**，决策落地后同步更新 `CONTEXT.md` / `docs/adr/`。

---

## 会话状态

| 字段 | 值 |
|------|-----|
| 开始时间 | 2026-07-30 |
| 当前阶段 | **Grilling 已完成**，可进入实现 |
| 已决议 | 10/10 + Trace 补充决议 |
| Grilling 进度 | ✅ 全部决议 |
| 路径策略 | **先 A 后 B**，A 阶段按 B 可演进方式设计 |
| 待决议 | 见下方问题队列 |

---

## 背景（来自上一轮讨论）

目标：在现有 OpenAI CS Agents Demo 基础上，构建 Python 航班订票助理，具备：

- 航班与用户 PostgreSQL 数据库
- RAG（混合检索 + Rerank）回答订票手册问题
- MCP / 本地工具调用完成订票、退票、改签
- DeepSeek Flash/Pro 模型分层路由（意图分类 + Agent 分配 + 歧义追问）
- 失败降级、熔断、Trace、上下文滑窗 + 摘要压缩
- 改签 Saga 事务与补偿回滚

**现有 Demo 现状**（代码事实）：

- 6 个 Specialist Agent + Triage Handoff（`airline/agents.py`）
- 业务数据为内存 Mock（`demo_data.py`），无真实 DB
- `faq_lookup_tool` 为关键词匹配，非 RAG
- 无用户身份校验（`cancel_flight` 等工具不校验归属）
- 已支持 DeepSeek OpenAI 兼容接口（`llm_config.py`）
- 前端为 Next.js + ChatKit 双栏 UI

---

## 问题队列（按依赖顺序）

| # | 问题 | 状态 | 决议 |
|---|------|------|------|
| Q1 | 项目定位：简历作品集 vs 可上线 PoC？ | ✅ 已决议 | **先 A 后 B** |
| Q2 | 用户身份：如何识别「当前用户」？ | ✅ 已决议 | **登录 + 用户专用 Agent + Admin 例外** |
| Q3 | 订票 vs 改签 vs 退票：领域术语边界 | ✅ 已决议 | **R1，确认号不变** |
| Q4 | 是否保留现有 Next.js UI？ | ✅ 已决议 | **U1，保留双栏 + 加登录页** |
| Q5 | PostgreSQL 部署方式 | ✅ 已决议 | **D1，docker-compose + pgvector** |
| Q6 | MCP：真 MCP Server vs 本地 function_tool 封装 | ✅ 已决议 | **M3，repository + function_tool，MCP-ready** |
| Q7 | RAG 知识库来源与规模 | ✅ 已决议 | **K1，自建中文 Markdown 手册** |
| Q8 | DeepSeek Flash/Pro 具体模型名 | ✅ 已决议 | **F1，v4-flash / v4-pro** |
| Q9 | 评测与验收标准 | ✅ 已决议 | **E1，作品集验收门槛** |
| Q10 | 权限模型：谁能操作谁的订单 | ✅ 已决议 | **B + X** |

## 实现进度（2026-07-30）

- [x] `docker-compose.yml` + `db/schema.sql` + `db/obs_schema.sql` + `db/seed.sql`
- [x] `db/pool`, `db/observability`, `db/repository/*`, `auth/*`
- [x] 登录 API + Cookie；聊天/ChatKit 需登录
- [x] 工具接 PostgreSQL + Saga 改签骨架 + RAG BM25
- [x] UI `/login` + `AuthGate`
- [x] LLM 调用自动写入 `obs.llm_calls`（`pipeline/logging_client.py` + `llm_config.configure_llm`）
- [x] 路由 / 熔断 / 上下文压缩（`pipeline/router|circuit_breaker|context_manager` + `server.respond`）
- [x] `eval/` 全量验收：`run_eval.py`（RAG 50 条 + auth 仓库 + Saga 确认号不变）
- [x] RAG 混合检索 + Rerank + **本地 BGE-M3 向量**（`sentence-transformers`）；金标 50 条达标
- [x] **B 薄壳** `mcp_server/` + `services/tool_facade.py`（stdio MCP，同 repository）

## 本地凭据速查（阶段 A 演示）

> 仅用于本地 `docker compose`；勿将含真实 API Key 的 `.env` 提交到公开仓库。

### PostgreSQL（Docker）

| 项 | 值 |
|----|-----|
| 主机 / 端口 | `localhost:5432` |
| 数据库名 | `airline` |
| 用户名 | `airline` |
| 密码 | `airline` |
| 连接串 | `postgresql://airline:airline@localhost:5432/airline` |

后端从项目根或 `python-backend` 下的 `.env` 读取 **`DATABASE_URL`**（见 `.env.example`）。

### Adminer（Web 管理库）

| 项 | 值 |
|----|-----|
| 地址 | http://localhost:8080 |
| 系统 | PostgreSQL |
| 服务器 | `postgres`（在 compose 网络内）或 `host.docker.internal` / `localhost`（本机直连时） |
| 用户名 / 密码 / 数据库 | `airline` / `airline` / `airline` |

### 应用登录（`public.users`，种子见 `db/seed.sql`）

| 用户名 | 密码 | 角色 | 说明 |
|--------|------|------|------|
| `zhangsan` | `demo123` | user | 订单确认号 **ABC123** |
| `lisi` | `demo123` | user | 订单确认号 **XYZ789** |
| `admin` | `demo123` | admin | 可代客操作，写 `obs.audit_log` |

Web 入口：http://localhost:3000/login（需先起 `uvicorn` + `npm run dev`）。

---

## Q1 记录（已决议）

**决议：先 A（简历作品集）后 B（可上线 PoC），两者不冲突，前提是 A 阶段避免「结构性偷懒」。**

### A → B 演进路线

```
阶段 A（4–6 周）                    阶段 B（+4–8 周）
─────────────────                  ─────────────────
能演示 + 能面试讲架构        →      能部署 + 能承压 + 能审计
账号密码登录（阶段 A）       →      JWT 强化 / OAuth / MFA
docker-compose 本地跑        →      云部署 + 监控告警
50 条 RAG 评测集             →      扩大语料 + 线上反馈闭环
工具层 RBAC（硬编码校验）    →      完整权限模型 + audit log
Langfuse 本地 / 自建 Trace   →      生产级可观测大盘
```

### 会冲突的做法（A 阶段禁止）

| 偷懒方式 | 为何阻碍 B |
|----------|-----------|
| 写操作继续用 `demo_data.py` 内存 Mock | B 要换整套数据层，Saga 白做 |
| 工具函数不校验 `user_id`，只靠 Prompt | B 要改每个工具，权限漏洞难补 |
| 改签多步 SQL 无 Saga 日志 | B 的回滚逻辑要重写 |
| Agent 直接拼 SQL | B 无法接 MCP / 审计 |
| RAG 无评测集，只靠体感 | B 无法量化「上线标准」 |

### 不冲突的做法（A 阶段就应坚持）

| 模块 | A 怎么做 | B 怎么升级 |
|------|----------|-----------|
| 数据 | PostgreSQL 从一开始 | 加连接池、读写分离、备份 |
| 身份 | 登录页 + `session.user_id` + `role`（user/admin） | JWT 强化、MFA、SSO |
| 工具 | MCP / function_tool 统一入口 + 权限校验 | 加 audit、限流 |
| 事务 | Saga + `booking_saga_log` | 加分布式锁、人工介入队列 |
| RAG | 混合检索 + Rerank + 评测脚本 | 扩文档、加线上反馈 |
| 部署 | `docker-compose up` | 换 K8s / 云服务，镜像不变 |

### 结论

**A 和 B 不冲突，冲突的是「A 里图省事走的捷径」。** 按上表做，A 交付后 B 主要是「加工程化」，不是「推翻重写」。

---

## Q1 原始记录（归档）

### 问题

**这个项目的首要目标是什么？**

- **A. 简历作品集** — 能演示、能讲清架构，面试时能答 RAG 命中率 / Saga 回滚 / 熔断 UX 等问题；允许部分 mock、不追求生产完备
- **B. 可上线 PoC** — 需要真实鉴权、完整测试、可部署；开发周期更长
- **C. 学习实验** — 优先覆盖技术栈（RAG + MCP + 多 Agent），业务可简化

### 我的推荐

**选 A（简历作品集）**，理由：

1. 你上一轮已明确问了「写简历能否找 Agent 开发工作」——说明作品集属性强
2. Demo 本身是 OpenAI 官方演示，在其上扩展比从零造轮子更高效
3. A 允许我们保留 Mock 降级路径（熔断、RAG 失败兜底），同时把「能讲清楚」的模块做扎实（Saga 回滚、权限测试、Trace）
4. 若选 B，Q2（鉴权）、Q9（评测集）会变成阻塞项，周期至少 ×2

### 选择 A 时的隐含范围

| 做 | 不做（或延后） |
|----|----------------|
| PostgreSQL 真实 CRUD + Saga | 支付网关对接 |
| RAG 混合检索 + 50 条评测集 | 百万级文档索引 |
| 工具层 RBAC + 越权测试用例 | OAuth / SSO 完整方案 |
| Flash/Pro 路由 + 熔断降级 | K8s 生产部署 |
| Langfuse/OTel Trace | 全链路压测报告 |

### 用户确认

先 A 后 B，作为前期目标与后期目标。

---

## Q2 记录（已决议）

**决议：A1 增强版 — 真实登录 + 用户专用 Agent + 数据隔离，Admin 可跨用户。**

### 用户原话

> 建一个数据库，agent 的使用需要登录，登录后才是用户专用 agent，而用户专用 agent 只能看到自己的数据信息，当然 admin 除外。

### 落地约束（实现时必须遵守）

| 规则 | 说明 |
|------|------|
| 未登录不可用 | 聊天入口需先通过登录页；无匿名会话 |
| Session 绑定身份 | 登录成功后 `session.user_id` + `session.role` 注入 Agent 上下文 |
| 数据隔离 | 普通 User：所有 DB 查询/写操作带 `WHERE user_id = :actor` |
| Admin 例外 | `role = admin` 时可查任意 User 的 Booking；操作记入 audit |
| 工具层硬校验 | 不靠 Prompt；`cancel_booking` 等工具校验 `booking.user_id == actor`（admin 跳过） |
| 用户专用 Agent | 同一套 Handoff 图，按 Session 过滤数据；非每用户一套模型 |

### 与初版 A1 的差异

用户要求**真实登录**（非下拉选用户 Mock），更接近 B 的鉴权形态——对 A→B 路径**有利**，无需后续推倒登录层。

### 数据模型（身份相关）

```
users(id, username, password_hash, role)   -- role: 'user' | 'admin'
bookings(id, user_id, flight_id, confirmation_no, ...)
sessions(id, user_id, token, expires_at)   -- 或 JWT 无状态
audit_log(id, actor_id, action, target, payload, created_at)
```

### 待 Q3/Q10 补充

- Admin 是否可**代客**下单/改签，还是仅查看+排障？
- 用户说他人确认号时，Agent 应回复「无权操作」还是「订单不存在」？（防枚举）

---

## Q3 记录（已决议）

**决议：R1 — 改签原地更新同一 Booking，确认号不变；不以「先退后订」实现改签。**

### 用户确认

> R1，改签用同一订单号吧。退票重订失败了怎么办，原来的票也没了。

### 为何不用「退票重订」（R2）

用户已点出 R2 的核心风险：

```
R2 错误顺序：取消原票 → 订新票
                    ↓ 若新订失败
              原票没了，用户无票 ← 灾难状态
```

这正是航空系统避免的做法。选 R1 的目的之一，就是**从领域规则上消灭这种中间态**。

### R1 改签 Saga（安全顺序）

```
Step 1  lock_new_seat        锁定新航班座位（原 Booking 不动）
Step 2  snapshot_old_state   快照旧 flight_id / seat（写入 saga_log）
Step 3  update_booking       UPDATE bookings SET flight_id=新, seat=新
                             WHERE confirmation_no=原号  ← 确认号不变
Step 4  release_old_seat     释放旧航班座位
Step 5  charge_diff          差价结算（可 mock）
```

**任一步失败 → 补偿回滚：**

| 失败点 | 用户状态 | 补偿动作 |
|--------|----------|----------|
| Step 1 | 原票仍在 | 无需补偿 |
| Step 3 | 原票仍在（UPDATE 未提交） | 释放 Step 1 锁定的新座 |
| Step 4 | 已改签到新航班 | 重试释放旧座（幂等） |
| Step 5 | 改签已完成 | 标记待支付，不撤销改签 |

**关键原则**：在 Step 3 成功之前，**绝不**把原 Booking 标为 cancelled。

### 三条业务路径（互不混淆）

| 用户意图 | 路径 | 确认号 |
|----------|------|--------|
| 「换一个航班」 | Rebooking（Saga 原地更新） | **不变** |
| 「不要了 / 退票」 | Cancellation | 原号作废 |
| 「再买一张」（无旧单） | New Booking | **新号** |

### 文档

- 术语：`CONTEXT.md` 已更新
- ADR：`docs/adr/0001-rebooking-in-place-not-cancel-rebook.md`

---

## Q4 记录（已决议）

**决议：U1 — 保留并扩展现有 Next.js + ChatKit 双栏 UI。**

### 落地范围

| 改动 | 说明 |
|------|------|
| 新增 `/login` 页 | 账号密码登录；成功后写 session / JWT cookie |
| 路由守卫 | 未登录跳转登录页；已登录进主界面 |
| 聊天请求带身份 | `Authorization` 或 cookie → 后端注入 `session.user_id` + `role` |
| 保留左栏 Agent 面板 | Handoff、Tool 调用、Guardrail 事件继续可视化（作品集亮点） |
| 右栏 ChatKit | 用户聊天不变；Admin 可加标识角标 |

### 不改

- 不砍掉 Agent 可视化（区别于 U3）
- 不重写前端框架（区别于 U2）

---

## Q5 记录（已决议）

**决议：D1 — docker-compose 一键启动 PostgreSQL（pgvector 镜像）。**

### 落地范围

```
docker-compose.yml
├── postgres (pgvector/pgvector:pg16)
│   ├── 业务库：users, flights, bookings, booking_saga_log, audit_log
│   └── RAG 库：document_chunks + embedding 向量列
├── adminer (可选，:8080 可视化管理)
└── volumes: pgdata 持久化
```

| 项 | 值 |
|----|-----|
| 连接串 | `postgresql://airline:airline@localhost:5432/airline` |
| 库账号 | 用户 `airline`，密码 `airline`，库名 `airline`（与 `docker-compose.yml` 中 `POSTGRES_*` 一致） |
| 初始化 | `db/schema.sql` + `db/seed.sql` 挂载到 `docker-entrypoint-initdb.d/` |
| 启动 | 根目录 `docker compose up -d` |
| Python | `asyncpg` 或 `SQLAlchemy 2.0 async` 连接 |

### A → B

B 阶段换云连接串（Neon/Supabase），schema 与代码不变。

### 用户确认

D1

---

## Q6 记录（已决议）

**决议：M3 — 分层架构，A 阶段 function_tool，B 阶段可加 MCP Server 外壳。**

### 代码分层

```
db/repository.py          ← 业务逻辑 + 权限校验 + Saga（唯一真相）
    ↑
airline/tools.py          ← @function_tool 薄封装（A 阶段 Agent 入口）
    ↑
mcp/server.py (B 阶段)    ← 同一 repository 的 MCP 传输层
```

### 原则

| 规则 | 说明 |
|------|------|
| 逻辑只在 repository | 禁止 tool 里直接拼 SQL |
| 工具层只做参数解析 + 调 repository | 与 Demo `tools.py` 形状一致 |
| MCP 是传输层 | B 阶段加壳，不改业务逻辑 |
| 权限在 repository | `actor_id` + `role` 每层校验 |

### 用户确认

M3

---

## Q7 记录（已决议）

**决议：K1 — 自建中文 Markdown 订票手册，迁入 RAG 索引。**

### 手册目录（初稿）

```
docs/manual/
├── 01-baggage.md          # 行李额度、超重费、丢失索赔
├── 02-rebooking.md        # 改签规则、手续费、确认号不变
├── 03-cancellation.md     # 退票政策、退款时效
├── 04-delay-compensation.md  # 延误补偿、酒店餐券
├── 05-seat-selection.md   # 选座、特殊服务座位
├── 06-wifi-amenities.md   # 机上 Wi-Fi、餐食
├── 07-check-in.md         # 值机、登机时间
├── 08-unaccompanied-minor.md  # 无人陪伴儿童（可选）
└── 09-faq-general.md      # 综合常见问题
```

| 项 | 值 |
|----|-----|
| 语言 | 简体中文（与 Demo 一致） |
| 规模 | 10–15 篇，切分后约 30–50 chunk |
| 来源 | 从 `faq_lookup_tool` 关键词答案迁移扩充 |
| 索引 | `rag/indexer.py` → pgvector + BM25（tsvector） |
| 评测 | 为 Q9 预留 `eval/rag_golden.jsonl` |

### 用户确认

K1（接受中文版）

---

## Q8 记录（已决议）

**决议：F1 — DeepSeek V4 分层路由，Flash / Pro 双模型。**

### 模型映射（用户提供的最新规格）

| 层级 | API 模型名 | 用途 |
|------|-----------|------|
| **Flash** | `deepseek-v4-flash` | 意图分类、FAQ/RAG、摘要、Guardrail、歧义追问 |
| **Pro** | `deepseek-v4-pro` | 订票/改签/退票写操作、复杂多步推理、Saga 编排 |

| 配置项 | 值 |
|--------|-----|
| BASE URL（OpenAI 格式） | `https://api.deepseek.com` |
| 上下文 | 1M tokens |
| 思考模式 | 两模型均支持；写操作默认开启思考模式（可配置） |
| 熔断降级 | Pro 失败 → Flash 简化 prompt |

### `.env` 示例

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
```

### 代码

`python-backend/llm_config.py` 已更新：`MODEL_FLASH` / `MODEL_PRO`；默认 `MODEL` 回退 Flash。

### 用户确认

F1，按 Flash/Pro 路由示意执行；模型名为 v4 系列（非旧版 chat/reasoner）。

---

## Q9 记录（已决议）

**决议：E1 — 作品集验收标准，可量化、可自动化、可演示。**

### 验收清单

| 类别 | 数量 | 通过标准 |
|------|------|----------|
| RAG 金标评测 | 50 条 | Recall@3 ≥ 85% |
| 工具调用用例 | 10 条 | 订票/改签/退票/查航班 + **越权拒绝** |
| Saga 回滚场景 | 3 条 | 改签 Step 3 失败 → 原票恢复 |
| 权限测试 | 5 条 | User 不可见他人订单；Admin 可见 |
| 端到端演示 | 1 套 | `docker compose up` → 登录 → 聊天 → 左栏可见 Agent 事件 |

### 评测资产路径

```
eval/
├── rag_golden.jsonl       # 50 条：question, expected_chunk_id, category
├── tool_cases.jsonl       # 10 条：intent, tools, expected_db_state
├── saga_rollback.jsonl    # 3 条：inject_failure_at_step, expected_compensation
├── auth_cases.jsonl       # 5 条：actor, target_booking, expect_allow/deny
└── run_eval.py            # 一键跑分，输出报告
```

### 用户确认

E1

---

## Q10 记录（已决议）

**决议：10a = B（Admin 全权代操作 + audit）；10b = X（统一「无法处理该确认号」）。**

| 规则 | 实现 |
|------|------|
| User 查自己订单 | `WHERE user_id = actor_id` |
| User 查他人确认号 | 返回「无法处理该确认号」，不区分不存在/无权 |
| Admin 代客操作 | 跳过 `user_id` 校验；`obs.audit_log` 记录 `actor_id` + `on_behalf_of_user_id` |
| 普通 User 写操作 | 同样写入 `obs.audit_log`（`on_behalf_of_user_id = NULL`） |
| 全链路 Trace | 每次请求 `trace_id`；见下方「可观测性」 |

### 用户确认

B + X；并要求加全链路 Trace。

---

## 补充决议：观测库 obs（2026-07-30 修订）

### audit_log：谁写入？

| Actor | 是否写入 audit_log | 说明 |
|-------|-------------------|------|
| **普通 User** | ✅ **每次写操作都写** | 订票 / 退票 / 改签 / 登录等 |
| **Admin 本人操作** | ✅ 写 | `on_behalf_of_user_id = NULL` |
| **Admin 代客操作** | ✅ 写 | 额外填 `on_behalf_of_user_id = 目标 User` |
| 只读查询 | ❌ 不写 audit | 写入 `obs.llm_calls` / `obs.rag_queries` 等 trace 表 |

> 之前文档仅强调 Admin 写 audit，已修正：**所有写操作均审计**，Admin 只是多一个代客字段。

### 全链路 Trace：记什么？

| 数据 | 存储表 | 是否全文 |
|------|--------|----------|
| LLM 请求 messages | `obs.llm_calls.request_messages` | ✅ JSONB 完整数组 |
| LLM 回复 | `obs.llm_calls.response_content` | ✅ TEXT 全文 |
| 思考模式 | `obs.llm_calls.thinking_content` | ✅ TEXT 全文 |
| API 原始响应 | `obs.llm_calls.raw_response` | ✅ JSONB |
| Tool 入参/出参 | `obs.tool_calls` | ✅ JSONB 全文 |
| RAG 各阶段 hits | `obs.rag_queries` | ✅ JSONB 全文 |
| 用户/助手每轮对话 | `obs.chat_messages` | ✅ 含 thinking_content |
| Span 元数据 | `obs.trace_spans` | 仅元数据；正文在专用表 |

**禁止**：仅写 `input_summary` 截断、仅 stdout、仅本地文件作为持久化。

### 库划分

```
PostgreSQL 实例
├── public.*     业务：users, flights, bookings, document_chunks, saga...
└── obs.*        观测：traces, llm_calls, tool_calls, audit_log, chat_messages...
```

A 阶段同实例两 schema；B 阶段 `obs` 可拆独立物理库（`OBS_DATABASE_URL`）。

DDL：`db/schema.sql` + `db/obs_schema.sql`

ADR：`docs/adr/0003-obs-schema-all-logs-in-db.md`

---

## 数据库设计总览（修订）

> 业务 DDL：`db/schema.sql`；观测 DDL：`db/obs_schema.sql`

### ER 关系

```
public.users ── bookings ── flights
public.booking_sagas ── booking_saga_steps
public.document_chunks（RAG 语料）

obs.traces 1──N trace_spans / llm_calls / tool_calls / rag_queries
obs.traces 1──N chat_messages / audit_log / guardrail_checks
```

### 表清单

| Schema | 表 | 职责 |
|--------|-----|------|
| public | users, auth_sessions | 身份 |
| public | flights, seat_locks, bookings | 业务 |
| public | booking_sagas, booking_saga_steps | Saga |
| public | document_chunks | RAG 语料 |
| obs | traces, trace_spans | Trace 骨架 |
| obs | **llm_calls** | LLM 全文 + 思考模式 |
| obs | tool_calls, rag_queries | Tool / RAG 全文 |
| obs | chat_messages, chat_summaries | 对话与压缩 |
| obs | **audit_log** | **所有写操作**审计 |
| obs | guardrail_checks, circuit_breaker_events, route_decisions | 护栏/熔断/路由 |
| obs | rag_feedback | Bad case |

---

## Grilling 决议总表（实现前必读）

| # | 决议 |
|---|------|
| Q1 | 先 A 后 B |
| Q2 | 登录 + 用户专用 Agent + Admin 例外 |
| Q3 | R1 改签，确认号不变，禁止先退后订 |
| Q4 | U1 保留双栏 UI + 登录页 |
| Q5 | D1 docker-compose + pgvector |
| Q6 | M3 repository + function_tool，MCP-ready |
| Q7 | K1 自建中文手册 Markdown |
| Q8 | deepseek-v4-flash / deepseek-v4-pro |
| Q9 | E1 评测门槛（50 RAG + 10 工具 + 3 Saga + 5 权限） |
| Q10 | B + X |
| + | 全链路 trace_spans |

---

## Q10 原始记录（归档）

### 问题

Admin 权限 + 确认号枚举防护。（选项见上文）

### 用户确认

B + X，加全链路 trace

---

## Q9 原始记录（归档）

### 问题

**阶段 A 怎样算「做完了」？**（选项 E1/E2/E3 见上文）

### 用户确认

E1

---

## Q8 原始记录（归档）

### 问题

**DeepSeek Flash / Pro 具体对应哪个 API 模型名？**

（初版选项含已过时的 `deepseek-chat` / `deepseek-reasoner`，以用户提供的 V4 规格为准。）

---

## Q7 原始记录（归档）

### 问题

**RAG 的「订票手册」内容从哪来？**（选项 K1/K2/K3 见上文）

### 用户确认

K1

---

## Q6 原始记录（归档）

### 问题

**Agent 如何调用 PostgreSQL？**（选项 M1/M2/M3 见上文）

### 用户确认

M3

---

## Q5 原始记录（归档）

### 问题

**PostgreSQL 怎么跑？**（选项 D1/D2/D3 见上文）

### 用户确认

D1

---

## Q4 原始记录（归档）

### 问题

**阶段 A 的前端怎么做？**（选项 U1/U2/U3 见上文）

### 用户确认

U1

---

## Q3 原始记录（归档）

### 问题

**「改签」和「退票重订」在你的业务里是不是同一件事？**

（选项 R1/R2/R3 见上文）

### 我的推荐

**R1（统一为改签）+ 取消走独立 Cancellation 路径**

---

## 决策日志

### 2026-07-30 — Q1：先 A 后 B

- **决议**：前期目标 A（简历作品集），后期目标 B（可上线 PoC）
- **约束**：A 阶段写操作走 PostgreSQL + Saga，身份走 `session.user_id` 抽象，禁止内存 Mock 写路径

### 2026-07-30 — Q2：登录 + 用户专用 Agent

- **决议**：必须登录；User 只看自己数据；Admin 可跨用户
- **文档**：术语已写入 `CONTEXT.md`

### 2026-07-30 — 观测库 obs 修订

- **audit_log**：所有 User/Admin 写操作均入库；Admin 代客填 `on_behalf_of_user_id`
- **llm_calls**：完整 messages / response / thinking_content，禁止截断
- **存储**：`obs` schema 为唯一持久化来源；ADR-0003

### 2026-07-30 — Q10：B + X + 全链路 Trace

- **Admin**：可代客操作，记入 `audit_log`
- **枚举防护**：统一「无法处理该确认号」
- **Trace**：`trace_spans` 表 + 左栏 UI 展示；ADR-0002

### 2026-07-30 — Q9：作品集验收 E1

- **决议**：50 RAG 金标 + 10 工具用例 + 3 Saga 回滚 + 5 权限用例；Recall@3 ≥ 85%
- **资产**：`eval/` 目录 + `run_eval.py`

### 2026-07-30 — Q8：DeepSeek V4 Flash/Pro 分层

- **决议**：F1；`deepseek-v4-flash` / `deepseek-v4-pro`；BASE URL `https://api.deepseek.com`
- **代码**：`llm_config.py` 已更新

### 2026-07-30 — Q7：自建中文手册 K1

- **决议**：`docs/manual/` 10–15 篇 Markdown；30–50 chunk；迁入混合 RAG
- **语言**：简体中文

### 2026-07-30 — Q6：M3 分层 MCP-ready

- **决议**：`repository` 承载业务逻辑；A 用 `function_tool`；B 可加 MCP Server 壳
- **约束**：禁止 tool 层直接拼 SQL

### 2026-07-30 — Q5：docker-compose + pgvector

- **决议**：D1；业务表与 RAG 向量同库；`docker compose up` 一键启动
- **初始化**：`db/schema.sql` + `db/seed.sql`

### 2026-07-30 — Q4：保留双栏 UI

- **决议**：U1；加登录页与路由守卫；保留 Agent 可视化面板
- **文档**：见 `content.md` Q4 落地范围表

### 2026-07-30 — Q3：R1 改签，确认号不变

- **决议**：Rebooking 原地更新；禁止先退后订；Saga 在 UPDATE 成功前不取消原票
- **ADR**：`docs/adr/0001-rebooking-in-place-not-cancel-rebook.md`

---

## 关联文档

- `CONTEXT.md` — 领域术语表（决议后创建/更新）
- `docs/adr/` — 架构决策记录（重大且难逆改时创建）
