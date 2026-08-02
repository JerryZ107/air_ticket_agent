-- 航班订票助理 — 观测/审计/Trace 专用 Schema（obs）
-- 原则：所有运行期日志、对话全文、LLM 完整 I/O、思考模式内容均入库，禁止仅写文件/stdout。
-- A 阶段：与业务库同 PostgreSQL 实例、独立 schema obs
-- B 阶段：可将 obs 拆至独立物理库（改连接串即可，表结构不变）

CREATE SCHEMA IF NOT EXISTS obs;

-- =============================================================================
-- 1. Trace 根记录（一次 HTTP / ChatKit 请求）
-- =============================================================================

CREATE TABLE obs.traces (
    id              UUID PRIMARY KEY,              -- trace_id，入口生成
    user_id         UUID NOT NULL,                 -- 逻辑 FK → public.users
    thread_id       VARCHAR(64),
    request_path    VARCHAR(256),
    client_ip       INET,
    status          VARCHAR(16) NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'ok', 'error', 'timeout')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    error_message   TEXT
);

CREATE INDEX idx_traces_user ON obs.traces(user_id, started_at DESC);
CREATE INDEX idx_traces_thread ON obs.traces(thread_id, started_at DESC);

-- =============================================================================
-- 2. Span 树（元数据；正文见 llm_calls / tool_calls / rag_queries）
-- =============================================================================

CREATE TABLE obs.trace_spans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID NOT NULL REFERENCES obs.traces(id) ON DELETE CASCADE,
    parent_span_id  UUID REFERENCES obs.trace_spans(id),
    span_name       VARCHAR(128) NOT NULL,
    span_type       VARCHAR(32) NOT NULL,
    -- intent_classify | rag_retrieve | agent_run | tool_call | saga_step
    -- | circuit_breaker | guardrail | context_compress | handoff
    status          VARCHAR(16) NOT NULL DEFAULT 'ok'
                    CHECK (status IN ('ok', 'error', 'timeout', 'skipped')),
    agent_name      VARCHAR(64),
    model           VARCHAR(64),
    latency_ms      INT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ
);

CREATE INDEX idx_spans_trace ON obs.trace_spans(trace_id, started_at);
CREATE INDEX idx_spans_type ON obs.trace_spans(span_type, started_at DESC);

-- =============================================================================
-- 3. LLM 完整调用记录（含思考模式全文，禁止截断/仅 summary）
-- =============================================================================

CREATE TABLE obs.llm_calls (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id            UUID NOT NULL REFERENCES obs.traces(id) ON DELETE CASCADE,
    span_id             UUID REFERENCES obs.trace_spans(id) ON DELETE SET NULL,
    call_index          INT NOT NULL DEFAULT 0,    -- 同 trace 内调用序号
    model               VARCHAR(64) NOT NULL,
    thinking_enabled    BOOLEAN NOT NULL DEFAULT false,
    -- 完整请求消息数组：[{role, content}, ...] 含 system / user / assistant / tool
    request_messages    JSONB NOT NULL,
    -- 完整模型输出（对用户可见部分）
    response_content    TEXT,
    -- 思考模式全文（DeepSeek V4 thinking / reasoning blocks）
    thinking_content    TEXT,
    -- 若 API 将 reasoning 与 content 分字段返回，原样存 raw_response
    raw_response        JSONB,
    prompt_tokens       INT,
    completion_tokens   INT,
    thinking_tokens     INT,
    total_tokens        INT,
    latency_ms          INT,
    status              VARCHAR(16) NOT NULL DEFAULT 'ok'
                        CHECK (status IN ('ok', 'error', 'timeout')),
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_llm_calls_trace ON obs.llm_calls(trace_id, call_index);
CREATE INDEX idx_llm_calls_model ON obs.llm_calls(model, created_at DESC);

-- =============================================================================
-- 4. Tool 完整入参/出参
-- =============================================================================

CREATE TABLE obs.tool_calls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID NOT NULL REFERENCES obs.traces(id) ON DELETE CASCADE,
    span_id         UUID REFERENCES obs.trace_spans(id) ON DELETE SET NULL,
    tool_name       VARCHAR(128) NOT NULL,
    input_json      JSONB NOT NULL,
    output_json     JSONB,
    status          VARCHAR(16) NOT NULL DEFAULT 'ok'
                    CHECK (status IN ('ok', 'error', 'denied')),
    latency_ms      INT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tool_calls_trace ON obs.tool_calls(trace_id, created_at);

-- =============================================================================
-- 5. RAG 检索全链路
-- =============================================================================

CREATE TABLE obs.rag_queries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id            UUID NOT NULL REFERENCES obs.traces(id) ON DELETE CASCADE,
    span_id             UUID REFERENCES obs.trace_spans(id) ON DELETE SET NULL,
    question            TEXT NOT NULL,
    bm25_hits           JSONB NOT NULL DEFAULT '[]',      -- [{chunk_id, score, content}]
    vector_hits         JSONB NOT NULL DEFAULT '[]',
    fused_hits          JSONB NOT NULL DEFAULT '[]',
    reranked_hits       JSONB NOT NULL DEFAULT '[]',
    final_chunk_ids     UUID[],
    top_confidence      REAL,
    latency_ms          INT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rag_queries_trace ON obs.rag_queries(trace_id);

CREATE TABLE obs.rag_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID REFERENCES obs.traces(id),
    user_id         UUID NOT NULL,
    question        TEXT NOT NULL,
    answer_snapshot TEXT,
    chunk_ids       UUID[],
    helpful         BOOLEAN,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- 6. 对话全文持久化（user / assistant 所有轮次）
-- =============================================================================

CREATE TABLE obs.chat_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID REFERENCES obs.traces(id),
    user_id         UUID NOT NULL,
    thread_id       VARCHAR(64) NOT NULL,
    sequence_no     INT NOT NULL,
    role            VARCHAR(16) NOT NULL
                    CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content         TEXT NOT NULL,
    thinking_content TEXT,                          -- assistant 思考模式全文（若有）
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (thread_id, sequence_no)
);

CREATE INDEX idx_chat_messages_thread ON obs.chat_messages(thread_id, sequence_no);
CREATE INDEX idx_chat_messages_user ON obs.chat_messages(user_id, created_at DESC);

CREATE TABLE obs.chat_summaries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID REFERENCES obs.traces(id),
    user_id         UUID NOT NULL,
    thread_id       VARCHAR(64) NOT NULL,
    summary_text    TEXT NOT NULL,
    compressed_from_seq INT,                        -- 被压缩的起始 sequence_no
    compressed_to_seq   INT,
    token_count     INT,
    model           VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- 7. 审计日志 —— 所有写操作（User + Admin），不仅 Admin
-- =============================================================================

CREATE TABLE obs.audit_log (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id                UUID REFERENCES obs.traces(id),
    actor_id                UUID NOT NULL,          -- 逻辑 FK → public.users
    actor_role              VARCHAR(16) NOT NULL,
    action                  VARCHAR(64) NOT NULL,
    -- booking.create | booking.cancel | booking.rebook | auth.login | ...
    target_type             VARCHAR(32) NOT NULL,
    target_id               UUID,
    on_behalf_of_user_id    UUID,                   -- Admin 代客时填写目标 User；本人操作则为 NULL
    before_state            JSONB,
    after_state             JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_actor ON obs.audit_log(actor_id, created_at DESC);
CREATE INDEX idx_audit_target ON obs.audit_log(target_type, target_id);
CREATE INDEX idx_audit_trace ON obs.audit_log(trace_id);
CREATE INDEX idx_audit_on_behalf ON obs.audit_log(on_behalf_of_user_id)
    WHERE on_behalf_of_user_id IS NOT NULL;

-- =============================================================================
-- 8. 护栏 / 熔断 / 路由
-- =============================================================================

CREATE TABLE obs.guardrail_checks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID NOT NULL REFERENCES obs.traces(id) ON DELETE CASCADE,
    span_id         UUID REFERENCES obs.trace_spans(id),
    guardrail_name  VARCHAR(64) NOT NULL,
    input_text      TEXT NOT NULL,
    passed          BOOLEAN NOT NULL,
    reasoning       TEXT,
    model           VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE obs.circuit_breaker_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID REFERENCES obs.traces(id),
    breaker_name    VARCHAR(64) NOT NULL,
    event_type      VARCHAR(32) NOT NULL,
    -- failure_recorded | opened | half_open | closed | fallback_invoked
    detail          JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE obs.route_decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID NOT NULL REFERENCES obs.traces(id) ON DELETE CASCADE,
    intent          VARCHAR(64),
    confidence      REAL,
    target_agent    VARCHAR(64),
    model_selected  VARCHAR(64),
    clarify_question TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
