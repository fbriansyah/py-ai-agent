import json

from datetime import datetime, timezone
from typing import Annotated, Literal
from typing_extensions import TypedDict
from dotenv import get_key

from models import Messages, MessageRole
from databases.memory import SessionLocal
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, Form as FastApiForm
from fastapi.responses import FileResponse, Response, StreamingResponse

from agents.rag import run_stream_agent
from agents.mongo_rag import MongoRagAgent

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior

router = APIRouter(
    prefix="/chat",
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
db_dependency = Annotated[Session, Depends(get_db)]

SESSION_ID = 'rag-session-05' # TODO: get from session

@router.get('/')
async def index(db: db_dependency) -> FileResponse:
    messages = db.query(Messages).filter(Messages.session_id == SESSION_ID).all()
    return Response(
        b'\n'.join(json.dumps(to_chat_message(m)).encode('utf-8') for m in messages),
        media_type='text/plain',
    )

@router.post('/')
async def post_chat(
    prompt: Annotated[str, FastApiForm()], db: db_dependency
) -> StreamingResponse:
    async def stream_messages():
        """Streams new line delimited JSON `Message`s to the client."""
        # stream the user prompt so that can be displayed straight away
        yield (
            json.dumps(
                {
                    'role': 'user',
                    'timestamp': datetime.now(tz=timezone.utc).isoformat(),
                    'content': prompt,
                }
            ).encode('utf-8')
            + b'\n'
        )
        result = ""
        messages = db.query(Messages).filter(Messages.session_id == SESSION_ID).all()
        message_history: list = []
        for m in messages:
            if m.role == MessageRole.USER:
                continue
            message_history.append(
                to_model_message(m)
            )
        mongo_uri = get_key(".env", "MONGO_URI")
        agent = MongoRagAgent(mongo_uri)
        # async for stream in run_stream_agent(prompt, messages=message_history):
        async for stream in agent.run_stream_agent(prompt, messages=message_history):
            async for text in stream.stream(debounce_by=0.01):
                # text here is a `str` and the frontend wants
                # JSON encoded ModelResponse, so we create one
                result = text
                m = Messages(
                    session_id=SESSION_ID,
                    role=MessageRole.AI,
                    message=text,
                    created_at=stream.timestamp(),
                )
                yield json.dumps(to_chat_message(m)).encode('utf-8') + b'\n'
        #  insert chat histories
        user_message = Messages(
            role=MessageRole.USER,
            session_id=SESSION_ID,
            message=prompt,
        )
        db.add(user_message)
        ai_message = Messages(
            role=MessageRole.AI,
            session_id=SESSION_ID,
            message=result,
        )
        db.add(ai_message)
        db.commit()
    return StreamingResponse(stream_messages(), media_type='text/plain')

class ChatMessage(TypedDict):
    """Format of messages sent to the browser."""

    role: Literal['user', 'model']
    timestamp: str
    content: str

def to_chat_message(m: Messages) -> ChatMessage:
    if m.role == MessageRole.USER:
        return {
            'role': 'user',
            'timestamp': m.created_at.isoformat(),
            'content': m.message,
        }
    elif m.role == MessageRole.AI:
        return {
            'role': 'model',
            'timestamp': m.created_at.isoformat(),
            'content': m.message,
        }
    raise UnexpectedModelBehavior(f'Unexpected message type for chat app: {m}')

def to_model_message(message: Messages) -> ModelMessage:
    if message.role != MessageRole.USER:
        return ModelResponse(
        parts=[TextPart(content=message.message)],
        timestamp=message.created_at.timestamp(),
    )