import asyncio
import json
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.engine import engine
from app.logging_setup import setup_logging
from app.prompts import build_system_prompt, format_search_results
from app.schemas import GenerateRequest
from core import memory
from core.search.brave_browse import search_and_browse
from app.session_manager import (
    append_session_message,
    ensure_session,
    expand_session_transcript,
    fetch_session_history,
    parse_session_id,
    summarise_session,
)

router = APIRouter()

setup_logging()
logger = logging.getLogger(__name__)

SEARCH_PATTERN = re.compile(r"\[SEARCH:\s*(.+?)\]", re.IGNORECASE)
EXPAND_PATTERN = re.compile(r"\[EXPAND:\s*(.+?)\]", re.IGNORECASE)


def _extract_search_query(text: str) -> str | None:
    if not text:
        return None
    match = SEARCH_PATTERN.search(text)
    if not match:
        return None
    query = match.group(1).strip()
    return query or None


def _extract_expand_id(text: str) -> str | None:
    if not text:
        return None
    match = EXPAND_PATTERN.search(text)
    if not match:
        return None
    session_id = match.group(1).strip()
    return session_id or None


def _append_user_system_prompt(base_prompt: str, user_prompt: str | None) -> str:
    if not user_prompt:
        return base_prompt
    return f"{base_prompt}\n\n### ADDITIONAL SYSTEM CONTEXT:\n{user_prompt}"


async def _recall_memories(prompt: str) -> list[str]:
    try:
        memories = memory.recall(prompt)
        if memories:
            logger.info("Memory recall returned %s items.", len(memories))
        return memories or []
    except Exception:
        logger.exception("Memory recall failed; continuing without context.")
        return []


async def _recall_session_summaries(prompt: str) -> list[dict]:
    try:
        results = memory.recall_with_metadata(
            prompt, n_results=5, source="chat_summary"
        )
        summaries = []
        for item in results:
            meta = item.get("metadata", {})
            summaries.append(
                {
                    "id": meta.get("session_id") or item.get("id"),
                    "title": meta.get("title") or "Untitled",
                    "summary": item.get("document") or "",
                }
            )
        if summaries:
            logger.info("Summary recall returned %s items.", len(summaries))
        return summaries
    except Exception:
        logger.exception("Summary recall failed; continuing without summaries.")
        return []


@router.websocket("/ws/chat/v2")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # receive JSON from Client (UI or LangChain)
            data = await websocket.receive_text()
            try:
                request_data = json.loads(data)
                if not isinstance(request_data, dict):
                    raise ValueError("Message must be a JSON object")

                if request_data.get("type") == "session_start":
                    session_id = request_data.get("session_id")
                    resolved = await ensure_session(session_id)
                    await websocket.send_json(
                        {
                            "type": "status",
                            "content": "session_ready",
                            "session_id": str(resolved) if resolved else None,
                        }
                    )
                    continue

                if request_data.get("type") == "session_end":
                    session_id = parse_session_id(request_data.get("session_id"))
                    if session_id:
                        asyncio.create_task(summarise_session(session_id, engine))
                    await websocket.send_json({"type": "status", "content": "session_closed"})
                    continue

                # convert dict to Pydantic model
                request = GenerateRequest(**request_data)

                await websocket.send_json({"type": "status", "content": "Thinking..."})

                session_id = await ensure_session(request.session_id)
                history = []
                if session_id and request.include_history:
                    history = await fetch_session_history(session_id)

                memories = await _recall_memories(request.prompt)
                summaries = await _recall_session_summaries(request.prompt)

                base_system = build_system_prompt(
                    memories=memories,
                    chat_history=history if request.include_history else [],
                    related_summaries=summaries,
                )
                base_system = _append_user_system_prompt(base_system, request.system_prompt)

                probe_request = GenerateRequest(**request_data)
                search_enforcer = (
                    "\n\n### CRITICAL INSTRUCTION:\n"
                    "If the user asks about a specific Event, Game, Score, News, or recent Fact, "
                    "you MUST output [SEARCH: <query>].\n"
                    "Do NOT answer from your internal knowledge for specific events."
                )
                probe_request.system_prompt = base_system + search_enforcer
                probe_request.max_tokens = min(request.max_tokens, 256)

                logger.info("Running search-intent probe.")
                probe_result = await engine.generate_text(probe_request)
                probe_text = probe_result.get("text", "")
                search_query = _extract_search_query(probe_text)
                expand_id = _extract_expand_id(probe_text)

                if session_id:
                    await append_session_message(session_id, "user", request.prompt)

                if not search_query and not expand_id:
                    logger.info("No search/expand requested; responding directly.")
                    await websocket.send_json({"type": "token", "content": probe_text})
                    await websocket.send_json({"type": "end", "content": ""})
                    if session_id:
                        await append_session_message(session_id, "assistant", probe_text)
                    continue

                expanded_transcripts = []
                if expand_id:
                    logger.info("Expand requested: %s", expand_id)
                    await websocket.send_json({"type": "status", "content": "Expanding past session..."})
                    expanded_text = await expand_session_transcript(expand_id)
                    if expanded_text and not (
                        expanded_text.startswith("[Error:")
                        or expanded_text.startswith("[System Error:")
                    ):
                        expanded_transcripts.append(expanded_text)
                    else:
                        logger.warning("Expand failed: %s", expanded_text)

                search_context = None
                if search_query:
                    logger.info("Search requested: %s", search_query)
                    await websocket.send_json({"type": "status", "content": "Searching the web..."})

                    browse_data = await search_and_browse(search_query)
                    if isinstance(browse_data, dict):
                        logger.info("Search returned %s results.", len(browse_data.get("results", [])))
                    else:
                        logger.warning("Search failed: %s", browse_data)
                    search_context = format_search_results(browse_data)

                final_system = build_system_prompt(
                    memories=memories,
                    chat_history=history if request.include_history else [],
                    related_summaries=summaries,
                    expanded_transcripts=expanded_transcripts,
                    search_context=search_context,
                )
                final_system = _append_user_system_prompt(final_system, request.system_prompt)
                request.system_prompt = final_system

                # stream tokens back
                response_text = ""
                async for token in engine.generate_stream(request):
                    response_text += token or ""
                    await websocket.send_json({"type": "token", "content": token})

                # end of message signal
                await websocket.send_json({"type": "end", "content": ""})
                if session_id:
                    await append_session_message(session_id, "assistant", response_text)
            except Exception as e:
                await websocket.send_json({"type": "error", "detail": str(e)})
            
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
