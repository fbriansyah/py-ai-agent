
import logfire
import asyncpg

from typing_extensions import AsyncGenerator
from contextlib import asynccontextmanager

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
@asynccontextmanager
async def database_connect(
    create_db: bool = False,
) -> AsyncGenerator[asyncpg.Pool, None]:
    server_dsn, database = (
        'postgresql://postgres:postgres@localhost:54320',
        'pydantic_ai_rag',
    )
    if create_db:
        with logfire.span('check and create DB'):
            conn = await asyncpg.connect(server_dsn)
            try:
                db_exists = await conn.fetchval(
                    'SELECT 1 FROM pg_database WHERE datname = $1', database
                )
                if not db_exists:
                    await conn.execute(f'CREATE DATABASE {database}')
            finally:
                await conn.close()

    pool = await asyncpg.create_pool(f'{server_dsn}/{database}')
    try:
        yield pool
    finally:
        await pool.close()

DB_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS doc_sections (
    id serial PRIMARY KEY,
    url text NOT NULL UNIQUE,
    title text NOT NULL,
    content text NOT NULL,
    -- text-embedding-3-small returns a vector of 1536 floats
    embedding vector(1536) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_doc_sections_embedding ON doc_sections USING hnsw (embedding vector_l2_ops);
"""

async def setup_schema(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(DB_SCHEMA)
            
async def search_docs(pool: asyncpg.Pool, embedding_json: str) -> list:
    return await pool.fetch(
        'SELECT url, title, content FROM doc_sections ORDER BY embedding <-> $1 LIMIT 8',
        embedding_json,
    )

async def create_embedding(pool: asyncpg.Pool, url: str, title: str, content: str, embedding: str) -> None:
    await pool.execute(
            'INSERT INTO doc_sections (url, title, content, embedding) VALUES ($1, $2, $3, $4)',
            url,
            title,
            content,
            embedding,
        )
async def check_embedding_exists(pool: asyncpg.Pool, url: str):
    return await pool.fetchval('SELECT 1 FROM doc_sections WHERE url = $1', url)