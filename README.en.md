# Airline Booking Customer-Service Agent

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/github/license/JerryZ107/air_ticket_agent)
![CI](https://github.com/JerryZ107/air_ticket_agent/actions/workflows/ci.yml/badge.svg)
![Eval](https://img.shields.io/badge/E2E%20Eval-37%2F37-brightgreen)
![RAG](https://img.shields.io/badge/RAG%20Recall%403-100%25-brightgreen)

A full-stack AI customer-service agent for an airline, built on the **OpenAI Agents SDK**. It demonstrates production-minded agent engineering: multi-agent orchestration, hybrid RAG, a real PostgreSQL business layer with RBAC, Saga transactions, full-stack observability, and an automated evaluation harness.

> Portfolio-grade demo (Phase A). Design decisions are recorded in [`docs/adr/`](docs/adr/) and [`content.md`](content.md). Full Chinese docs: [README.md](README.md).

## Highlights

- **Multi-agent orchestration** — 1 triage agent + 5 specialists (flight info / booking & cancellation / seat & special services / FAQ / refunds & compensation) with Handoff routing and Flash/Pro model tiering.
- **Deterministic fast paths** — High-confidence FAQ and flight-status queries bypass the LLM agent and call tools directly (flight status answered in 20–300 ms with no narration drift).
- **Hybrid RAG** — 17 Chinese policy manuals chunked by heading; keyword + PostgreSQL tsvector BM25 + BGE-M3 vectors, lightweight rerank, confidence/coverage rejection thresholds, and automatic sub-question splitting for compound questions.
- **Real data layer + RBAC** — PostgreSQL + asyncpg; permission checks enforced in the repository layer, not prompts. Regular users can only touch their own bookings; admins can act on behalf with full audit trail; confirmation-number enumeration is mitigated with a uniform denial message.
- **Rebooking Saga** — In-place update keeps the confirmation number unchanged; atomic seat locking, step logging, and compensation rollback eliminate the dangerous "cancel-then-rebook" intermediate state.
- **Observability (`obs` schema)** — Every request gets a trace ID; full LLM I/O (including reasoning), tool arguments/results, RAG hits, chat transcripts, audit logs, guardrail checks, circuit-breaker events, and routing decisions are persisted to PostgreSQL.
- **Resilience** — Relevance + jailbreak input guardrails (fail-open, fully logged), agent circuit breaker, sliding-window context compression with summarization, login rate limiting.
- **Automated evaluation** — 37 end-to-end test cases plus golden-set RAG recall, permission, session-isolation, and Saga acceptance checks, all reproducible with one command and enforced by CI.

## Evaluation results (measured 2026-08-03)

| Check | Result |
|-------|--------|
| 37 end-to-end batch cases | **37/37 passed**, zero heuristic issues |
| RAG golden Recall@3 (50 cases) | **100%** (threshold ≥ 85%) |
| Permission / authorization cases | 3/3 |
| Session isolation | 8/8 |
| Rebooking Saga (confirmation unchanged) | 1/1 |

## Quick start

```bash
# 1. PostgreSQL + pgvector (schema & seed auto-loaded)
docker compose up -d

# 2. Configure python-backend/.env (see .env.example; DEEPSEEK_API_KEY required)

# 3. Backend
cd python-backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8001

# 4. Frontend
cd ui && npm install && npm run dev
```

Open http://localhost:3000/login. Demo accounts: `zhangsan` / `lisi` / `admin` (all `demo123`).

## Tests

```bash
python -m pytest -q                                   # unit + DB integration (auto-skips without DB)
python scripts/run_ques_batch.py                      # 37-case E2E batch (needs running backend)
python eval/run_eval.py                               # RAG golden / auth / session / Saga acceptance
```

CI (`.github/workflows/ci.yml`) provisions a `pgvector/pgvector:pg16` service container and runs the full suite on every push.

## Architecture

```
Next.js + ChatKit UI
    │ /chatkit
    ▼
FastAPI ──► intent router ──► FAQ / flight-status direct paths
    │                        └──► Triage Agent ──Handoff──► 5 specialist agents
    ▼                                                     │ (guardrails on input)
tool_facade ──► repository (bookings / saga / auth, RBAC)
    │
    ▼
PostgreSQL: public (business) + obs (traces / LLM / tools / audit)
```

## License

MIT. Evolved from the OpenAI CS Agents Demo for learning and demonstration purposes.
