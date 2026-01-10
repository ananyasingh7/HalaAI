import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from app.config import settings
from app.logging_setup import setup_logging
from app.prompts import SUMMARY_SYSTEM_PROMPT
from app.schemas import GenerateRequest
from core import memory
from data.sql import expander
from data.sql.database import (
    append_history,
    create_session,
    get_session,
    list_active_sessions_older_than,
    update_session_summary,
)

setup_logging()
logger = logging.getLogger(__name__)


def _parse_json_payload(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _format_transcript(history: list[dict[str, Any]], max_messages: int | None = None) -> str:
    if not history:
        return ""
    trimmed = history[-max_messages:] if max_messages else history
    lines = []
    for msg in trimmed:
        role = str(msg.get("role", "unknown")).upper()
        content = msg.get("content", "")
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_summary_response(text: str) -> tuple[str, str]:
    payload = _parse_json_payload(text) or {}
    title = str(payload.get("title") or "").strip()
    summary = str(payload.get("summary") or "").strip()

    if title or summary:
        return title or "Conversation Summary", summary

    # Fallback: treat first line as title, rest as summary
    stripped = text.strip()
    if not stripped:
        return "Conversation Summary", ""

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if not lines:
        return "Conversation Summary", ""

    title = lines[0][:80]
    summary = " ".join(lines[1:])[:2000] if len(lines) > 1 else ""
    return title, summary


async def ensure_session(session_id_str: str) -> uuid.UUID | None:
    if not session_id_str:
        return None
    try:
        session_id = uuid.UUID(session_id_str)
    except ValueError:
        logger.warning("Invalid session_id received: %s", session_id_str)
        return None

    await asyncio.to_thread(create_session, session_id=session_id)
    return session_id


def parse_session_id(session_id_str: str | None) -> uuid.UUID | None:
    if not session_id_str:
        return None
    try:
        return uuid.UUID(session_id_str)
    except ValueError:
        logger.warning("Invalid session_id received: %s", session_id_str)
        return None


async def append_session_message(session_id: uuid.UUID, role: str, content: str) -> None:
    await asyncio.to_thread(append_history, session_id=session_id, role=role, content=content)


async def fetch_session_history(session_id: uuid.UUID) -> list[dict[str, Any]]:
    session = await asyncio.to_thread(get_session, session_id)
    if not session:
        return []
    return list(session.history or [])


async def expand_session_transcript(session_id_str: str) -> str:
    return await asyncio.to_thread(expander.fetch_full_session, session_id_str)


async def summarise_session(
    session_id: uuid.UUID,
    engine,
    max_messages: int | None = None,
) -> None:
    session = await asyncio.to_thread(get_session, session_id)
    if not session:
        return
    if session.is_summarized:
        return

    history = list(session.history or [])
    transcript = _format_transcript(history, max_messages=max_messages)
    if not transcript:
        update_session_summary(session_id, title="Empty Conversation", summary="")
        return

    prompt = f"TRANSCRIPT:\n{transcript}"
    request = GenerateRequest(
        prompt=prompt,
        system_prompt=SUMMARY_SYSTEM_PROMPT.strip(),
        max_tokens=256,
        priority=settings.priorities.background,
    )

    logger.info("Summarising session %s (%s messages).", session_id, len(history))
    chunks: list[str] = []
    async for token in engine.generate_stream(request):
        if token:
            chunks.append(token)
    response_text = "".join(chunks)

    title, summary = _parse_summary_response(response_text)
    await asyncio.to_thread(
        update_session_summary,
        session_id=session_id,
        title=title,
        summary=summary,
        mark_inactive=True,
    )

    if summary:
        memory.memorize(
            summary,
            source="chat_summary",
            metadata={"session_id": str(session_id), "title": title},
            doc_id=str(session_id),
        )


async def sweep_stale_sessions(engine, idle_seconds: int = 600) -> None:
    cutoff = datetime.utcnow() - timedelta(seconds=idle_seconds)
    stale = await asyncio.to_thread(list_active_sessions_older_than, cutoff)
    if stale:
        logger.info("Found %s stale active sessions.", len(stale))

    for session in stale:
        await summarise_session(session.id, engine)


async def start_session_sweeper(
    engine, interval_seconds: int = 1800, idle_seconds: int = 600
) -> None:
    logger.info("Session sweeper started (interval=%ss idle=%ss).", interval_seconds, idle_seconds)
    while True:
        try:
            await sweep_stale_sessions(engine, idle_seconds=idle_seconds)
        except Exception:
            logger.exception("Session sweeper failed.")
        await asyncio.sleep(interval_seconds)
