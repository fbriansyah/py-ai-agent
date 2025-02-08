from typing import Annotated
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends
from starlette import status
from models import Messages, MessageRole
from database import SessionLocal
from agents.chat import ChatAgent
from pydantic import Literal, TypedDict
from pydantic_ai.messages import (
    ModelMessage, 
    ModelRequest, 
    TextPart, 
    ModelResponse,
    UserPromptPart,
    UnexpectedModelBehavior
)

router = APIRouter(
    prefix="/webhook/default",
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
db_dependency = Annotated[Session, Depends(get_db)]

class MessageRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=1000)
    
chat_agent = ChatAgent()

def to_model_message(message: Messages) -> ModelMessage:
    if message.role != MessageRole.USER:
        return ModelResponse(
        parts=[TextPart(content=message.message)],
        timestamp=message.created_at.timestamp(),
    )

class ChatMessage(TypedDict):
    """Format of messages sent to the browser."""

    role: Literal['user', 'model']
    timestamp: str
    content: str


def to_chat_message(m: ModelMessage) -> ChatMessage:
    first_part = m.parts[0]
    if isinstance(m, ModelRequest):
        if isinstance(first_part, UserPromptPart):
            return {
                'role': 'user',
                'timestamp': first_part.timestamp.isoformat(),
                'content': first_part.content,
            }
    elif isinstance(m, ModelResponse):
        if isinstance(first_part, TextPart):
            return {
                'role': 'model',
                'timestamp': m.timestamp.isoformat(),
                'content': first_part.content,
            }
    raise UnexpectedModelBehavior(f'Unexpected message type for chat app: {m}')

@router.post("/", status_code=status.HTTP_200_OK)
async def default_webhook(message_request: MessageRequest, db: db_dependency):
    messages = db.query(Messages).filter(Messages.session_id == message_request.session_id).all()
    message_history: list = []
    for m in messages:
        if m.role == MessageRole.USER:
            continue
        message_history.append(
            to_model_message(m)
        )
    
    result = await chat_agent.chat(message_request.message, message_history)
    user_message = Messages(
        role=MessageRole.USER,
        session_id=message_request.session_id,
        message=message_request.message,
    )
    db.add(user_message)
    
    ai_message = Messages(
        role=MessageRole.AI,
        session_id=message_request.session_id,
        message=result.data,
    )
    db.add(ai_message)
    db.commit()
    
    return {"message": message_request.message, "session_id": message_request.session_id, "content": result.data}