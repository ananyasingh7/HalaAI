import logging
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

from app.logging_setup import setup_logging

# --- CONFIGURATION ---
DATABASE_URL = os.getenv(
    "HALA_HISTORY_DB_URL", "postgresql://ananyasingh@localhost:5432/hala_ai_history"
)

setup_logging()
logger = logging.getLogger(__name__)

class ChatSession(SQLModel, table=True):
    __tablename__ = "sessions"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(default="New Conversation")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)
    is_summarized: bool = Field(default=False)
    
    # The RAG Summary (for the AI to read quickly)
    summary: Optional[str] = Field(default=None)
    
    # The Full History (for the AI to "Deep Dive" into)
    # Stores: [{"role": "user", "content": "..."}]
    history: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def init_db():
    logger.info("Ensuring history DB schema is up to date.")
    SQLModel.metadata.create_all(engine)


def get_session(session_id: uuid.UUID) -> Optional[ChatSession]:
    with Session(engine) as db:
        return db.get(ChatSession, session_id)


def create_session(session_id: uuid.UUID | None = None, title: str = "New Conversation") -> ChatSession:
    session_id = session_id or uuid.uuid4()
    with Session(engine) as db:
        existing = db.get(ChatSession, session_id)
        if existing:
            return existing

        now = datetime.utcnow()
        chat_session = ChatSession(
            id=session_id,
            title=title,
            created_at=now,
            last_active_at=now,
            updated_at=now,
            is_active=True,
            is_summarized=False,
            history=[],
        )
        db.add(chat_session)
        db.commit()
        db.refresh(chat_session)
        return chat_session


def append_history(session_id: uuid.UUID, role: str, content: str) -> None:
    now = datetime.utcnow()
    entry = {"role": role, "content": content, "timestamp": now.isoformat()}

    with Session(engine) as db:
        chat_session = db.get(ChatSession, session_id)
        if not chat_session:
            chat_session = ChatSession(
                id=session_id,
                title="New Conversation",
                created_at=now,
                last_active_at=now,
                updated_at=now,
                is_active=True,
                is_summarized=False,
                history=[entry],
            )
            db.add(chat_session)
        else:
            history = list(chat_session.history or [])
            history.append(entry)
            chat_session.history = history
            chat_session.last_active_at = now
            chat_session.updated_at = now
            chat_session.is_active = True

        db.commit()


def update_session_summary(
    session_id: uuid.UUID,
    title: str | None,
    summary: str | None,
    mark_inactive: bool = True,
) -> None:
    now = datetime.utcnow()
    with Session(engine) as db:
        chat_session = db.get(ChatSession, session_id)
        if not chat_session:
            return

        if title:
            chat_session.title = title
        if summary:
            chat_session.summary = summary
        chat_session.is_summarized = True
        if mark_inactive:
            chat_session.is_active = False
        chat_session.updated_at = now
        db.commit()


def mark_inactive(session_id: uuid.UUID) -> None:
    with Session(engine) as db:
        chat_session = db.get(ChatSession, session_id)
        if not chat_session:
            return
        chat_session.is_active = False
        chat_session.updated_at = datetime.utcnow()
        db.commit()


def list_active_sessions_older_than(cutoff: datetime) -> List[ChatSession]:
    with Session(engine) as db:
        statement = select(ChatSession).where(
            ChatSession.is_active == True,  # noqa: E712
            ChatSession.last_active_at < cutoff,
        )
        results = db.exec(statement).all()
        return list(results)


def delete_session(session_id: uuid.UUID) -> bool:
    with Session(engine) as db:
        chat_session = db.get(ChatSession, session_id)
        if not chat_session:
            return False
        db.delete(chat_session)
        db.commit()
        return True
