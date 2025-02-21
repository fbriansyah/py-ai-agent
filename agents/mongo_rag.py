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

from databases.mongo import MongoClient

@dataclass

class Deps:
    openai: AsyncOpenAI
    mongo: MongoClient

class MongoRagAgent():
    agent = Agent('openai:gpt-4o', deps_type=Deps)
    def __init__(self, mongo_uri = ""):
        if mongo_uri == "":
            mongo_uri = get_key(".env", "MONGO_URI")
        if mongo_uri is None:
            logfire.error("MONGO_URI not found")
            return
        self.mongo_client = MongoClient(mongo_uri, "pyAgent")
    
    async def run_agent(self, question: str, messages: list[ModelMessage]) -> RunResult[str]:
        """Entry point to run the agent and perform RAG based question answering."""
        openai = AsyncOpenAI()
        
        logfire.instrument_openai(openai)

        logfire.info('Asking "{question}"', question=question)

        deps = Deps(openai=openai, mongo=self.mongo_client)
        answer = await self.agent.run(question, deps=deps, message_history=messages)
        
        return answer
    
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
                    'group': 1, 
                    'title': 1, 
                    'content': 1
                }
            }
        ]
        context.deps.mongo.ping()
        collection = context.deps.mongo.get_collection("doc_sections")
        data = await collection.aggregate(pipeline)
        # data = await context.deps.mongo.vector_search("doc_sections", pipeline)
        rows = []
        async for dt in data:
            row = {
                "group": dt["group"],
                "title": dt["title"],
                "content": dt["content"]
            }
            rows.append(row)
        return '\n\n'.join(
            f'# {row["title"]}\nDocumentation group:{row["group"]}\n\n{row["content"]}\n'
            for row in rows
        )