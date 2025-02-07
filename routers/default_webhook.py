from typing import Annotated
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Path
from starlette import status
from models import Messages, MessageRole
from database import SessionLocal

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
    

@router.post("/", status_code=status.HTTP_200_OK)
async def default_webhook(message_request: MessageRequest, db: db_dependency):
    system_message = Messages(
        role=MessageRole.SYSTEM,
        session_id=message_request.session_id,
        message="You are a helpful assistant.",
    )
    db.add(system_message)
    
    user_message = Messages(
        role=MessageRole.USER,
        session_id=message_request.session_id,
        message=message_request.message,
    )
    db.add(user_message)
    db.commit()
    return {"message": user_message.message, "session_id": user_message.session_id, "kind": user_message.role, "created_at": user_message.created_at}