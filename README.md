# 航班订票智能客服 Agent

基于 OpenAI Agents SDK 的 **Python 航班订票助理**：真实 PostgreSQL 订单、**RAG 订票手册**、多专员 Agent 编排、可观测与审计。适用于本地演示、作品集与中小团队 PoC，**不是**开箱即用的 SaaS。

---

## 功能概览

| 能力 | 说明 |
|------|------|
| **多 Agent 分诊** | 分诊、航班信息、订票改签、选座、FAQ、延误补偿等专员，支持 Handoff |
| **业务工具** | 查单、航班状态、搜航班、退改签、换座等，经 `services/tool_facade.py` 统一访问数据库 |
| **RAG 政策问答** | `docs/manual` 手册 → 按标题切块 → 关键词 + BM25 + 向量 + Rerank；高置信 FAQ 路由可直连检索结果 |
| **登录与权限** | JWT / Cookie；普通用户仅能操作本人订单；`admin` 可全库列表、`list_customer_bookings` 代查旅客 |
| **严守工具与手册** | 订单/状态以工具返回为准；政策以手册检索为准；未收录须明确「无法确认」 |
| **可观测 `obs`** | Trace、LLM 调用、工具入出、对话全文、路由决策、护栏、审计日志（见 `db/obs_schema.sql`） |
| **前端** | Next.js + ChatKit 双栏（对话 + Runner 轨迹）；另提供 `/api/chat` 便于国内批量测试 |

---

## 架构简图

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│  ui (3000)  │────▶│  python-backend (8001)                    │
│  ChatKit    │     │  FastAPI · Agents SDK · pipeline/router   │
└─────────────┘     │       │                    │               │
                    │       ▼                    ▼               │
                    │  airline/tools      rag/retriever          │
                    │       │                    │               │
                    │       └──────┬─────────────┘               │
                    │              ▼                             │
                    │     services/tool_facade                   │
                    │              ▼                             │
                    │     db/repository  +  obs (审计/日志)      │
                    └──────────────────┬─────────────────────────┘
                                       ▼
                              PostgreSQL (pgvector)
```

- **业务表**：`public.*`（`db/schema.sql` + `db/seed.sql`）
- **观测表**：`obs.*`（`db/obs_schema.sql`）
- **可选 MCP**：stdio 子进程仅暴露 **写操作**（取消/改签/换座）；读操作与会话绑定走本地 `function_tool`（默认 **关闭 MCP**，见下文）

---

## 快速开始

### 1. 启动数据库

```bash
docker compose up -d
```

- PostgreSQL：`localhost:5432`，库名 `airline`，用户/密码 `airline` / `airline`
- Adminer：http://localhost:8080（可选，查表）

### 2. 配置环境变量

在 `python-backend/.env` 或项目根 `.env` 中配置（勿提交真实密钥）：

```env
DEEPSEEK_API_KEY=你的密钥
# 或 OPENAI_API_KEY + OPENAI_BASE_URL

DATABASE_URL=postgresql://airline:airline@localhost:5432/airline

# 嵌入模型（默认本地 BGE-M3，首次启动会下载）
EMBEDDING_BACKEND=local
EMBEDDING_DEVICE=cpu

# 多用户生产建议保持 false（工具身份绑 HTTP 登录会话）
AIRLINE_USE_MCP_TOOLS=false
```

### 3. 启动后端

```bash
cd python-backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

启动时会自动：索引 `docs/manual`、补全向量（若可用）。

### 4. 启动前端

```bash
cd ui
npm install
npm run dev
```

浏览器打开 http://localhost:3000/login

**Windows 一键**（Docker + 后端 + 前端各开窗口）：

```powershell
.\scripts\start_demo.ps1
```

### 5. 健康检查

```bash
curl http://127.0.0.1:8001/health
```

---

## 演示账号

| 用户名 | 密码 | 说明 |
|--------|------|------|
| `zhangsan` | `demo123` | 旅客；订单确认号 **ABC123**（NY900） |
| `lisi` | `demo123` | 旅客；订单 **XYZ789**（NY802，种子数据可能为已取消） |
| `admin` | `demo123` | 管理员；可查全库最近订单、代查指定旅客 |

---

## API 摘要

| 接口 | 说明 |
|------|------|
| `POST /api/auth/login` | 登录，返回 token（同时写 Cookie） |
| `POST /api/chat` | 简易对话（Bearer token），适合脚本批量测 |
| `POST /chatkit` | ChatKit 流式协议（前端使用） |
| `GET /api/trace/{trace_id}` | 查看单次请求的 trace / LLM / tool（本人或 admin） |

---

## 测试与评测

### 批量业务问答（`ques.md`）

```bash
# 需先启动后端；默认 37 题（跳过 destructive 写操作）
python scripts/run_ques_batch.py

# 含退改签等写操作（慎用，会改库）
python scripts/run_ques_batch.py --include-destructive

# 只跑部分题
python scripts/run_ques_batch.py --id-prefix R
```

结果：`eval/ques_batch_results.json`；启发式分析：`python scripts/analyze_ques_results.py`

### 打印 QA 日志（数据库 + 批量结果）

```bash
python scripts/qa.py
python scripts/qa.py --id M07 A04
```

对话持久化在 `obs.chat_messages`（`/api/chat` 会写入 user/assistant 与 `trace_id`）。

### RAG

```bash
python scripts/diagnose_rag.py          # 单题检索诊断
python scripts/embed_manual.py          # 重索引手册
python eval/run_eval.py                 # 金标 Recall（见 eval/）
```

---

## MCP（可选）

本仓库 MCP 为 **B 阶段薄壳**：与 `tool_facade` 共用领域逻辑，**不是**对外远程 MCP 产品。

| 项 | 说明 |
|----|------|
| 默认 | `AIRLINE_USE_MCP_TOOLS=false`，全部走本地 `function_tool`，**按登录用户绑会话** |
| 开启后 | `main.py` 拉起 stdio 子进程；仅 **订票/选座专员** 挂载 MCP；工具为 `cancel_flight`、`rebook_flight`、`update_seat` |
| 身份 | 子进程依赖 `AIRLINE_SESSION_USERNAME` 或调试变量 `AIRLINE_MCP_ACTOR`，**不适合多用户并发** |
| 独立运行 | `cd python-backend && python -m mcp_server` |
| Cursor 配置 | 参考 `docs/mcp-cursor.json` |

远程 MCP + OAuth 2.1 未实现；生产多用户请用 **HTTP JWT + 本地工具** 路径。

---

## 项目结构

```
openai-cs-agents-demo-main/
├── python-backend/          # FastAPI、Agent、RAG、auth、pipeline
│   ├── airline/             # agents、tools、context、grounding
│   ├── rag/                 # 切块、检索、rerank
│   ├── mcp_server/          # 可选 MCP 写操作
│   ├── services/tool_facade.py
│   └── main.py
├── ui/                      # Next.js 前端
├── db/                      # schema、obs、seed、迁移
├── docs/manual/             # RAG 订票手册 Markdown
├── scripts/                 # 批量测试、qa.py、诊断脚本
├── eval/                    # 批量结果与分析、金标
├── ques.md                  # 批量问题集 JSON
├── docker-compose.yml
├── RUNBOOK.md               # 运维与 RAG/MCP 补充说明
└── content.md               # 架构决议与实现记录（Grilling）
```

---

## 上线前注意（中小团队 PoC）

- 更换演示密码、启用 HTTPS、`COOKIE_SECURE=1`
- 生产关闭或严格限制写操作与 `destructive` 批量题
- 手册更新后执行重索引与 `ques` 回归
- 数据库备份与 `obs` 留存策略
- 详见此前讨论的 P0：CI 门禁、health 含 DB、降级与人工兜底

---

## 相关文档

- [RUNBOOK.md](RUNBOOK.md) — 本地运行、RAG 环境变量、MCP 细节
- [ques.md](ques.md) — 批量测试题与类别
- [eval/A04_optimization.md](eval/A04_optimization.md) — 管理员代查旅客示例立项
- [docs/manual/README.md](docs/manual/README.md) — 手册编写说明

---

## 技术栈

- Python 3.11+、FastAPI、OpenAI Agents SDK、asyncpg、pgvector
- 嵌入：sentence-transformers（BGE-M3 等，可配置）
- LLM：DeepSeek / OpenAI 兼容接口（`llm_config.py`）
- 前端：Next.js、ChatKit

---

## 许可与声明

源于 OpenAI CS Agents Demo 的演进实现，用于学习与演示。演示数据与手册内容不代表任何真实航司政策；生产使用需自行合规审查与接口对接。
