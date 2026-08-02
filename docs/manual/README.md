# 订票手册（Policy Manual）

**RAG 语料目录**：本文件夹内除本 README 外的 `*.md` 均由 `index_manuals()` 索引。

对应 `CONTEXT.md` 中的 **Policy Manual**；路径约定见 K1 决议：`docs/manual/`（非 `docs/reference/`、非仓库外层目录）。

## 来源说明

| 类型 | 说明 |
|------|------|
| `00`–`16` 系列 Markdown | **Demo 航司「云翔航空」** 旅客政策与场景库（虚构；`eval/rag_golden.jsonl` 金标对齐 `01`–`06`） |
| `00-regulatory-excerpt.md` | 交通运输部公开规章摘录（附政府网链接） |

`docs/` 下其余内容（`adr/`、`mcp-cursor.json`）为工程文档，**不**参与 RAG。

## 文件一览

| 文件 | 主题 |
|------|------|
| `00-regulatory-excerpt.md` | 法规摘录 |
| `01-baggage.md` | 行李 |
| `02-rebooking.md` | 改签 |
| `03-cancellation.md` | 退票 |
| `04-delay-compensation.md` | 延误补偿 |
| `05-seat-selection.md` | 选座 |
| `06-wifi-amenities.md` | 机上服务 |
| `07-check-in.md` | 值机 |
| `08-unaccompanied-minor.md` | 无陪儿童 |
| `09-faq-general.md` | 综合 FAQ |
| `10`–`15` | 国际、危险品、常旅客等 |
| `16-rag-scenarios.md` | 场景化问答 |

索引实现：`python-backend/rag/indexer.py`（`POLICY_MANUAL_DIR` 可覆盖路径）。
