import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select

from app.logging_setup import setup_logging
from data.sql.database import engine, ChatSession, delete_session

setup_logging()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])


def _session_to_dict(session: ChatSession) -> dict:
    return {
        "id": str(session.id),
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "last_active_at": session.last_active_at.isoformat() if session.last_active_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "is_active": session.is_active,
        "is_summarized": session.is_summarized,
        "summary": session.summary,
        "history": session.history or [],
    }


@router.get("/sessions")
def list_sessions():
    with Session(engine) as db:
        rows = db.exec(select(ChatSession)).all()
        return [_session_to_dict(row) for row in rows]


@router.get("/session")
def get_session(session_id: str = Query(..., description="Session UUID")):
    try:
        parsed = uuid.UUID(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID") from e

    with Session(engine) as db:
        session = db.get(ChatSession, parsed)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return _session_to_dict(session)


@router.delete("/session")
def remove_session(session_id: str = Query(..., description="Session UUID")):
    try:
        parsed = uuid.UUID(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid session_id UUID") from e

    if not delete_session(parsed):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@router.get("/summaries")
def list_summaries():
    with Session(engine) as db:
        rows = db.exec(select(ChatSession).where(ChatSession.is_summarized == True)).all()  # noqa: E712
        return [
            {
                "id": str(row.id),
                "title": row.title,
                "summary": row.summary,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
