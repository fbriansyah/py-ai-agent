from __future__ import annotations as _annotations

import asyncio
import logfire
import re
import unicodedata
from dataclasses import dataclass

import asyncpg
import httpx
import pydantic_core
from openai import AsyncOpenAI
from pydantic import TypeAdapter
from dotenv import get_key

from pydantic_ai import RunContext
from pydantic_ai.result import RunResult
from pydantic_ai.agent import Agent
from pydantic_ai.messages import (
    ModelMessage,
)

from databases.pg_vector import (
    database_connect as vector_db_connect, 
    setup_schema,
    search_docs,
    create_embedding,
    check_embedding_exists
)
from databases.mongo import MongoClient
logfire.configure(send_to_logfire='if-token-present', token=get_key(".env", "LOGFIRE_KEY"))
logfire.instrument_asyncpg()

@dataclass
class Deps:
    openai: AsyncOpenAI
    pool: asyncpg.Pool


agent = Agent('openai:gpt-4o', deps_type=Deps)


@agent.tool
async def retrieve(context: RunContext[Deps], search_query: str) -> str:
    """Retrieve documentation sections based on a search query.

    Args:
        context: The call context.
        search_query: The search query.
    """
    with logfire.span(
        'create embedding for {search_query=}', search_query=search_query
    ):
        embedding = await context.deps.openai.embeddings.create(
            input=search_query,
            model='text-embedding-3-small',
        )
        

    assert (
        len(embedding.data) == 1
    ), f'Expected 1 embedding, got {len(embedding.data)}, doc query: {search_query!r}'
    embedding = embedding.data[0].embedding
    # embedding_json = pydantic_core.to_json(embedding).decode()
    # rows = await search_docs(context.deps.pool, embedding_json)
    pipeline = [
        {
            '$vectorSearch': {
                'index': 'embedding_index', 
                'path': 'embedding', 
                'filter': {}, 
                'queryVector': embedding, 
                'numCandidates': 150, 
                'limit': 20
            }
        }, 
        {
            '$project': {
                '_id': 0, 
                'slug': 1, 
                'title': 1, 
                'content': 1
            }
        }
    ]
    mongo_uri = get_key(".env", "MONGO_URI")
    if mongo_uri is None:
        logfire.error("MONGO_URI not found in .env file")
        return
    mongo_client = MongoClient(mongo_uri, "pyAgent")
    mongo_client.ping()
    data = await mongo_client.vector_search("doc_sections", pipeline)
    rows = []
    async for dt in data:
        row = {
            "slug": dt["slug"],
            "title": dt["title"],
            "content": dt["content"]
        }
        rows.append(row)
    return '\n\n'.join(
        f'# {row["title"]}\nDocumentation URL:{row["slug"]}\n\n{row["content"]}\n'
        for row in rows
    )

async def run_stream_agent(question: str, messages: list[ModelMessage]):
    """Run the streaming agent while keeping resources open."""
    openai = AsyncOpenAI()
    
    async with vector_db_connect(False) as pool:
        deps = Deps(openai=openai, pool=pool)
        async with agent.run_stream(question, deps=deps, message_history=messages) as stream:
            yield stream
    

async def run_agent(question: str, messages: list[ModelMessage]) -> RunResult[str]:
    """Entry point to run the agent and perform RAG based question answering."""
    openai = AsyncOpenAI()
    
    logfire.instrument_openai(openai)

    logfire.info('Asking "{question}"', question=question)

    async with vector_db_connect(False) as pool:
        deps = Deps(openai=openai, pool=pool)
        answer = await agent.run(question, deps=deps, message_history=messages)
    
    return answer

async def build_search_db():
    """Build the search database."""
    doc_json = get_key(".env", "DOCS_JSON")
    if doc_json == "":
        raise ValueError('DOCS_JSON not set in .env file')
    async with httpx.AsyncClient() as client:
        response = await client.get(doc_json)
        response.raise_for_status()
    sections = sessions_ta.validate_json(response.content)

    openai = AsyncOpenAI()
    logfire.instrument_openai(openai)

    async with vector_db_connect(True) as pool:
        with logfire.span('create schema'):
            await setup_schema(pool)

        sem = asyncio.Semaphore(10)
        async with asyncio.TaskGroup() as tg:
            for section in sections:
                tg.create_task(insert_doc_section(sem, openai, pool, section))


async def insert_doc_section(
    sem: asyncio.Semaphore,
    openai: AsyncOpenAI,
    pool: asyncpg.Pool,
    section: DocsSection,
) -> None:
    async with sem:
        url = section.url()
        exists = await check_embedding_exists(pool, url)
        if exists:
            logfire.info('Skipping {url=}', url=url)
            return

        with logfire.span('create embedding for {url=}', url=url):
            embedding = await openai.embeddings.create(
                input=section.embedding_content(),
                model='text-embedding-3-small',
            )
        assert (
            len(embedding.data) == 1
        ), f'Expected 1 embedding, got {len(embedding.data)}, doc section: {section}'
        embedding = embedding.data[0].embedding
        embedding_json = pydantic_core.to_json(embedding).decode()
        
        await create_embedding(pool, url, section.title, section.content, embedding_json)


@dataclass
class DocsSection:
    id: int
    parent: int | None
    path: str
    level: int
    title: str
    content: str

    def url(self) -> str:
        url_path = re.sub(r'\.md$', '', self.path)
        return (
            f'https://febriannr/{url_path}/#{slugify(self.title, "-")}'
        )

    def embedding_content(self) -> str:
        return '\n\n'.join((f'path: {self.path}', f'title: {self.title}', self.content))


sessions_ta = TypeAdapter(list[DocsSection])


def slugify(value: str, separator: str, unicode: bool = False) -> str:
    """Slugify a string, to make it URL friendly."""
    # Taken unchanged from https://github.com/Python-Markdown/markdown/blob/3.7/markdown/extensions/toc.py#L38
    if not unicode:
        # Replace Extended Latin characters with ASCII, i.e. `žlutý` => `zluty`
        value = unicodedata.normalize('NFKD', value)
        value = value.encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(rf'[{separator}\s]+', separator, value)

