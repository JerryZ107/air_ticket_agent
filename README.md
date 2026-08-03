# ✈️ 航班订票智能客服 Agent

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/github/license/JerryZ107/air_ticket_agent)
![CI](https://github.com/JerryZ107/air_ticket_agent/actions/workflows/ci.yml/badge.svg)
![Eval](https://img.shields.io/badge/E2E%20Eval-37%2F37-brightgreen)
![RAG](https://img.shields.io/badge/RAG%20Recall%403-100%25-brightgreen)

基于 **OpenAI Agents SDK** 的航空公司智能客服系统：多 Agent 编排 + 混合检索 RAG + 真实 PostgreSQL 业务层 + RBAC 权限 + Saga 事务 + 全链路可观测，并自带一套**可量化、可自动复现**的评测体系。

> 这是一个简历作品集项目（阶段 A：本地演示 / 作品集；阶段 B：可上线 PoC），不是开箱即用的 SaaS。设计决策记录在 [`docs/adr/`](docs/adr/) 与 [`content.md`](content.md)。

---

## 亮点（简历速览）

| 能力 | 说明 |
|------|------|
| **多 Agent 编排** | 1 个分诊 Agent + 5 个专员（航班信息 / 订退改 / 选座特殊服务 / FAQ / 退款补偿），Handoff 转接；写操作 Agent 用 Pro 模型，其余用 Flash 模型分层 |
| **确定性直连路径** | 高置信 FAQ 与航班状态查询**绕过 Agent 直接调工具**：省 token、零旁白、结果稳定（航班状态查询实测 20–300ms） |
| **混合检索 RAG** | 17 篇中文订票手册 → 标题切块 → 关键词 + PostgreSQL tsvector BM25 + BGE-M3 向量 → 轻量 Rerank → 置信度/词覆盖双阈值拒答；复合问题自动拆分子检索 |
| **真实数据层 + 权限** | PostgreSQL + asyncpg；登录/JWT + RBAC 硬校验（repository 层，非 prompt 层）；普通用户只能操作本人订单，admin 可代客并写审计；防枚举统一回复「无法处理该确认号」 |
| **改签 Saga** | 确认号不变，事务内原子扣减余票 + 状态快照 + 步骤留痕 + 失败补偿回滚，从规则上消灭「先退后订」的中间态 |
| **全链路可观测 `obs`** | 每次请求一个 trace_id：LLM 请求/响应/思考全文、工具出入参、RAG 各阶段命中、对话全文、审计日志、护栏检查、熔断事件、路由决策全部落库 |
| **工程韧性** | 相关性 + 越狱检测输入护栏（fail-open + 全量审计）、Agent 熔断器、上下文滑窗 + 摘要压缩、登录限流 |
| **自动化评测** | 37 题端到端批量测试 + RAG 金标 Recall + 越权/会话隔离/Saga 验收，全部可一键复现（见下） |

---

## 架构

```mermaid
flowchart LR
    U["用户 / Next.js + ChatKit 前端"] -->|"/chatkit"| API["FastAPI"]
    API --> R["pipeline/router 意图路由"]
    R -->|高置信 FAQ| FD["FAQ 直连"]
    R -->|高置信航班状态| SD["航班状态直连"]
    R --> T["Triage Agent"]
    T -->|Handoff| A1["航班信息专员"]
    T -->|Handoff| A2["订票改签专员"]
    T -->|Handoff| A3["选座/特殊服务专员"]
    T -->|Handoff| A4["FAQ 专员"]
    T -->|Handoff| A5["退款补偿专员"]
    A1 & A2 & A3 & A4 & A5 --> G["输入护栏：相关性 + 越狱检测"]
    A1 & A2 & A3 --> TF["services/tool_facade"]
    TF --> REP["db/repository：bookings / saga / auth"]
    REP --> PG[("PostgreSQL public 业务库")]
    A4 & FD --> RAG["rag/retriever 混合检索 + Rerank"]
    RAG --> PG
    API --> OBS[("PostgreSQL obs 观测库")]
```

一次完整请求的时序：

```mermaid
sequenceDiagram
    participant U as 用户
    participant API as FastAPI
    participant Router as 意图路由
    participant Agent as 专员 Agent
    participant Tool as tool_facade
    participant DB as PostgreSQL
    U->>API: 登录 + 消息
    API->>Router: classify_and_route()
    Router-->>API: intent + 置信度
    alt 高置信 FAQ / 航班状态
        API->>Tool: 确定性直连
    else
        API->>Agent: Runner.run_streamed()
        Agent->>Tool: function_tool 调用
        Tool->>DB: 权限校验 + SQL / Saga 事务
        DB-->>Tool: 结果
        Tool-->>Agent: 工具输出
    end
    API->>DB: 写入 trace / LLM / tool / audit
    API-->>U: 流式回复 + Runner 轨迹（前端可视）
```

---

## 评测结果（2026-08-03 实测）

| 验收项 | 结果 | 复现方式 |
|--------|------|----------|
| 37 题端到端批量（RAG / 工具 / 权限 / admin 代客 / 分诊） | **37/37 通过，启发式检查零问题** | `python scripts/run_ques_batch.py && python scripts/analyze_ques_results.py` |
| RAG 金标 Recall@3（50 条） | **100%**（门槛 ≥ 85%） | `python eval/run_eval.py` |
| 越权 / 权限用例 | 3/3 | 同上 |
| 会话隔离 | 8/8 | 同上 |
| 改签 Saga（确认号不变） | 1/1 | 同上 |
| 航班状态直连延迟 | 20–300ms，零旁白 | 批量结果 `elapsed_ms` |

CI 会在每次 push 时自动运行单测 + 数据库集成测试（详见 [.github/workflows/ci.yml](.github/workflows/ci.yml)）。

---

## 快速开始

### 1. 启动数据库

```bash
docker compose up -d
```

- PostgreSQL：`localhost:5432`，库名 `airline`，用户/密码 `airline` / `airline`
- Adminer（可选）：http://localhost:8080

### 2. 配置环境变量

复制 `.env.example` 为 `.env`（**勿提交真实密钥**）：

```env
DEEPSEEK_API_KEY=你的密钥
DATABASE_URL=postgresql://airline:airline@localhost:5432/airline
EMBEDDING_BACKEND=local   # 本地 BGE-M3，首次启动自动下载
EMBEDDING_DEVICE=cpu
AIRLINE_USE_MCP_TOOLS=false
```

### 3. 启动后端

```bash
cd python-backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

启动时自动索引 `docs/manual` 并补齐向量。

### 4. 启动前端

```bash
cd ui
npm install
npm run dev
```

浏览器打开 http://localhost:3000/login

Windows 一键脚本：`.\scripts\start_demo.ps1`

健康检查：`curl http://127.0.0.1:8001/health`（含数据库连通性，DB 不可用时返回 503）

### 演示账号

| 用户名 | 密码 | 说明 |
|--------|------|------|
| `zhangsan` | `demo123` | 旅客；订单 **ABC123**（NY900） |
| `lisi` | `demo123` | 旅客；订单 **XYZ789**（NY802，可能为已取消） |
| `admin` | `demo123` | 管理员；全库列表 + `list_customer_bookings` 代查 |

---

## 测试与 CI

```bash
# 单元 + 数据库集成测试（自动跳过无数据库用例）
python -m pytest -q

# 端到端批量（需后端运行；默认跳过写操作）
python scripts/run_ques_batch.py

# RAG 检索诊断
python scripts/diagnose_rag.py

# 全套验收（RAG 金标 / 越权 / 会话 / Saga）
python eval/run_eval.py
```

GitHub Actions 使用 `pgvector/pgvector:pg16` 服务容器自动初始化 schema + seed，每次 push 自动跑测试（[ci.yml](.github/workflows/ci.yml)）。

---

## 项目结构

```
├── python-backend/          # FastAPI · Agents SDK · pipeline
│   ├── airline/             # agents / tools / guardrails / session 绑定
│   ├── pipeline/            # 意图路由 / 直连路径 / 上下文压缩 / 熔断
│   ├── rag/                 # 切块 / 混合检索 / rerank
│   ├── mcp_server/          # 可选 MCP 写操作薄壳
│   ├── services/tool_facade.py
│   └── main.py
├── ui/                      # Next.js + ChatKit（对话 + Runner 轨迹）
├── db/                      # schema / seed / obs / migrations
├── docs/                    # 手册语料 + ADR 决策记录
├── scripts/                 # 批量测试 / 诊断 / 一键启动
├── eval/                    # 金标集 + 验收脚本 + 结果
└── tests/                   # pytest 单测 + DB 集成测试
```

## 路线图（A → B）

| 阶段 A（当前） | 阶段 B（可上线 PoC） |
|----------------|----------------------|
| 账号密码登录 + RBAC | OAuth 2.1 / MFA / SSO |
| docker-compose 本地跑 | 云部署 + 监控告警 |
| 50 条 RAG 金标 + CI | 线上反馈闭环（`obs.rag_feedback`） |
| 工具层 RBAC + 审计 | 完整权限模型 + 多租户 |
| 本地 trace / 观测库 | 生产级可观测大盘 |

## 许可

MIT（源自 OpenAI CS Agents Demo 的演进实现，用于学习与演示；演示数据与手册内容不代表任何真实航司政策）。

English version: [README.en.md](README.en.md)
