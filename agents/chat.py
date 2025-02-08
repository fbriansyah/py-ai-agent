import os
import httpx

from dataclasses import dataclass
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import ModelMessage
from pydantic_ai.result import RunResult
# from pydantic_ai.models import KnownModelName

class ChatAgent():
    agent = Agent('openai:gpt-4o', result_type=str)

    async def chat(self, message: str, messages: list[ModelMessage]) -> RunResult[str]:
        result = await self.agent.run(message, message_history=messages)
        return result