-- Run on existing DBs: docker exec -i airline-postgres psql -U airline -d airline < db/migrations/001_pgvector_embeddings.sql

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
