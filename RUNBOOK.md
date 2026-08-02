# 本地运行（阶段 A 实现）

## 1. 启动数据库

```bash
docker compose up -d
```

## 2. 后端

```bash
cd python-backend
pip install -r requirements.txt
# 配置 DEEPSEEK_API_KEY 等于 .env
uvicorn main:app --reload --port 8001
```

## 3. 前端

```bash
cd ui
npm install
npm run dev
```

或 Windows 一键：`.\scripts\start_demo.ps1`（Docker + 后端 + 前端各开窗口）

访问 http://localhost:3000/login

演示账号：

- `zhangsan` / `demo123`（订单 ABC123）
- `lisi` / `demo123`（订单 XYZ789）
- `admin` / `demo123`

## 架构要点

- 业务表：`public.*`（`db/schema.sql`）
- 观测库：`obs.*`（`db/obs_schema.sql`）— audit、trace、LLM 全文、对话、RAG 查询
- 工具层：`db/repository` + `airline/tools.py`
- 登录：Cookie `session_token`

## RAG 与评测

- 手册：`docs/manual/*.md`，启动时自动 `index_manuals()` + **本地 BGE-M3** 写入 `document_chunks.embedding`
- 环境变量（`python-backend/.env` 或项目根 `.env`）：
  - `EMBEDDING_BACKEND=local`（默认；`openai` 可走兼容 Embedding API）
  - `EMBEDDING_MODEL=BAAI/bge-m3`（备选：`Zhinao/ChinseModernBert-Embedding` 等，需设对 `EMBEDDING_DIM`）
  - `EMBEDDING_DEVICE=cpu`（有 NVIDIA GPU 可设 `cuda`）
- 已有库升级：`001_pgvector_embeddings.sql` 后执行 `002_embedding_bge_m3_1024.sql`
- 需 **pgvector** 镜像（`docker-compose.yml` 已配置）
- 生成 50 条金标：`python scripts/gen_rag_golden.py`
- 跑分：`python eval/run_eval.py`（Recall@3 ≥ 85%）

## B 阶段：MCP Server 薄壳

与 `airline/tools.py` 共用 **`services/tool_facade.py`** → `db/repository/*`（M3 分层）。

```bash
cd python-backend
pip install mcp
python -m mcp_server
```

- 默认 **stdio**；环境变量 `AIRLINE_MCP_ACTOR=zhangsan`（写操作身份）
- Cursor / Claude Desktop：参考 `docs/mcp-cursor.json` 合并到 MCP 配置
- 工具：`faq_lookup_tool`、`list_bookings`、`flight_status_tool`、`search_flights`、`cancel_flight`、`rebook_flight`、`update_seat`
- **Agents SDK**：`AIRLINE_USE_MCP_TOOLS=true`（默认）时，`main.py` 启动 `MCPServerStdio` 子进程，专员 Agent 通过 MCP 调 PG 工具；`tools.py` 仅保留演示/UI 类 `function_tool`
- 关闭 MCP 回退：`AIRLINE_USE_MCP_TOOLS=false`（全部走 `function_tool` → `tool_facade`）
