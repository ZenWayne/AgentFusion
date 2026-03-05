-- Migration: Add memory keywords table for advanced memory search
-- Date: 2026-02-10

-- Create agent_memory_keywords table
CREATE TABLE IF NOT EXISTS agent_memory_keywords (
    id SERIAL PRIMARY KEY,
    memory_key VARCHAR(255) NOT NULL REFERENCES agent_memories(memory_key) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES "User"(id) ON DELETE CASCADE,
    keyword VARCHAR(255) NOT NULL,
    weight FLOAT DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for efficient keyword search
CREATE INDEX IF NOT EXISTS idx_memory_keywords_keyword ON agent_memory_keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_memory_keywords_user_key ON agent_memory_keywords(user_id, memory_key);
CREATE INDEX IF NOT EXISTS idx_memory_keywords_user_kw ON agent_memory_keywords(user_id, keyword);

-- Add index on memory_type for filtering
CREATE INDEX IF NOT EXISTS idx_agent_memories_type ON agent_memories(memory_type);

-- Add index on is_active for filtering
CREATE INDEX IF NOT EXISTS idx_agent_memories_active ON agent_memories(is_active);

-- Add composite index for common queries
CREATE INDEX IF NOT EXISTS idx_agent_memories_search ON agent_memories(user_id, memory_type, created_at, is_active)
WHERE is_active = true;

-- Note: For vector search (semantic), install pgvector extension:
-- CREATE EXTENSION IF NOT EXISTS vector;
-- ALTER TABLE agent_memories ADD COLUMN embedding vector(1536);
-- CREATE INDEX IF NOT EXISTS idx_memories_embedding ON agent_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
