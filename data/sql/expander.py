import logging
import uuid

from sqlmodel import Session

from app.logging_setup import setup_logging
from data.sql.database import engine, ChatSession

setup_logging()
logger = logging.getLogger(__name__)

def fetch_full_session(session_id_str: str) -> str:
    """
    Retrieves the full JSON transcript for a specific session ID.
    """
    logger.info("Deep Dive: Expanding Session %s...", session_id_str)
    try:
        s_id = uuid.UUID(session_id_str)
        with Session(engine) as db:
            session = db.get(ChatSession, s_id)
            if not session or not session.history:
                return "[Error: Session not found or empty]"
            
            # Format JSONB into a readable transcript
            transcript = f"--- FULL TRANSCRIPT (Session {s_id}) ---\n"
            for msg in session.history:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                transcript += f"{role}: {content}\n\n"
            
            return transcript + "--- END TRANSCRIPT ---"
            
    except Exception as e:
        return f"[System Error: {e}]"
