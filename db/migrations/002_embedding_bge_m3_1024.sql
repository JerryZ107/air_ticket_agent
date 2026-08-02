-- Resize embedding column for BGE-M3 (1024). Run after 001 if you had vector(1536).

DROP INDEX IF EXISTS idx_chunks_embedding;
ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding;
ALTER TABLE document_chunks ADD COLUMN embedding vector(1024);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
