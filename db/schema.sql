-- 航班订票助理 — 业务库 Schema（public）
-- A 阶段：pgvector 镜像启用 embedding；无向量时仍可用关键词检索

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- 1. 身份与鉴权
-- =============================================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(64) NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    VARCHAR(100),
    role            VARCHAR(16) NOT NULL DEFAULT 'user'
                    CHECK (role IN ('user', 'admin')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE auth_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX idx_auth_sessions_expires ON auth_sessions(expires_at);

-- =============================================================================
-- 2. 航班与座位
-- =============================================================================

CREATE TABLE flights (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flight_no       VARCHAR(16) NOT NULL,
    origin          VARCHAR(64) NOT NULL,
    destination     VARCHAR(64) NOT NULL,
    departure_at    TIMESTAMPTZ NOT NULL,
    arrival_at      TIMESTAMPTZ NOT NULL,
    seats_total     INT NOT NULL CHECK (seats_total > 0),
    seats_available INT NOT NULL CHECK (seats_available >= 0),
    price_cents     INT NOT NULL CHECK (price_cents >= 0),
    status          VARCHAR(16) NOT NULL DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled', 'delayed', 'cancelled', 'departed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (flight_no, departure_at)
);

CREATE INDEX idx_flights_route_date ON flights(origin, destination, departure_at);
CREATE INDEX idx_flights_status ON flights(status);

CREATE TABLE seat_locks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flight_id       UUID NOT NULL REFERENCES flights(id),
    seat            VARCHAR(8) NOT NULL,
    saga_id         UUID,
    booking_id      UUID,
    locked_until    TIMESTAMPTZ NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'locked'
                    CHECK (status IN ('locked', 'released', 'consumed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_seat_locks_flight_seat ON seat_locks(flight_id, seat) WHERE status = 'locked';
CREATE INDEX idx_seat_locks_saga ON seat_locks(saga_id);

-- =============================================================================
-- 3. 订单
-- =============================================================================

CREATE TABLE bookings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    flight_id           UUID NOT NULL REFERENCES flights(id),
    confirmation_no     VARCHAR(10) NOT NULL UNIQUE,
    seat                VARCHAR(8) NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'confirmed'
                        CHECK (status IN ('confirmed', 'cancelled', 'pending_rebook')),
    price_paid_cents    INT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_bookings_user ON bookings(user_id);
CREATE INDEX idx_bookings_flight ON bookings(flight_id);
CREATE INDEX idx_bookings_status ON bookings(status);
CREATE INDEX idx_bookings_confirmation ON bookings(confirmation_no);

-- =============================================================================
-- 4. 改签 Saga
-- =============================================================================

CREATE TABLE booking_sagas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id      UUID NOT NULL REFERENCES bookings(id),
    actor_id        UUID NOT NULL REFERENCES users(id),
    target_flight_id UUID REFERENCES flights(id),
    status          VARCHAR(16) NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed', 'compensated')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

CREATE TABLE booking_saga_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    saga_id         UUID NOT NULL REFERENCES booking_sagas(id) ON DELETE CASCADE,
    step_no         INT NOT NULL,
    action          VARCHAR(32) NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    status          VARCHAR(16) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'done', 'failed', 'compensated')),
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (saga_id, step_no)
);

CREATE INDEX idx_saga_steps_saga ON booking_saga_steps(saga_id);

-- =============================================================================
-- 5. RAG 知识库（业务语料，非运行日志）
-- =============================================================================

CREATE TABLE document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file     VARCHAR(256) NOT NULL,
    chunk_index     INT NOT NULL,
    title           VARCHAR(256),
    content         TEXT NOT NULL,
    content_tsv     TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    embedding       vector(1024),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_file, chunk_index)
);

CREATE INDEX idx_chunks_source ON document_chunks(source_file);
CREATE INDEX idx_chunks_tsv ON document_chunks USING GIN(content_tsv);
CREATE INDEX idx_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops);
