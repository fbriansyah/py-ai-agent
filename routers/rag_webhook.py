from fastapi import APIRouter, Depends
from starlette import status
from agents.rag import build_search_db, run_agent
from databases.memory import SessionLocal
from sqlalchemy.orm import Session
from typing import Annotated
from pydantic import BaseModel, Field
from models import Messages, MessageRole
from pydantic_ai.messages import (
    TextPart, 
    ModelResponse
)

router = APIRouter(
    prefix="/webhook/rag",
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
    

@router.post("/build", status_code=status.HTTP_200_OK)
async def build_rag_webhook():
    try:
        await build_search_db()
        return {"message": "RAG webhook called"}
    except Exception as e:
        return {"message": f"Error: {e}"}
    
@router.post("/chat", status_code=status.HTTP_200_OK)
async def chat_rag_webhook(message_request: MessageRequest, db: db_dependency):
    try:
        messages = db.query(Messages).filter(Messages.session_id == message_request.session_id).all()
        message_history: list = []
        for m in messages:
            if m.role == MessageRole.USER:
                continue
            message_history.append(
                ModelResponse(
                    parts=[TextPart(content=m.message)],
                    timestamp=m.created_at.timestamp(),
                )
            )
        result = await run_agent(messages=message_request.message, message_history=message_history)
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
        return {"message": result.data}
    except Exception as e:
        return {"message": f"Error: {e}"}