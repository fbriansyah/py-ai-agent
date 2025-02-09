from databases.memory import Base
from sqlalchemy import Column, Integer, String, Enum as SqlEnum, DateTime
from sqlalchemy.sql import func
from enum import Enum

class MessageRole(Enum):
    AI = 'AI'
    USER = 'USER'
    SYSTEM =  'SYSTEM'

    def __str__(self):
        return self.value

class Messages(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, index=True)
    role = Column(SqlEnum(MessageRole), default=MessageRole.USER)
    session_id = Column(String)
    message = Column(String)
    created_at = Column(DateTime, default=func.now())