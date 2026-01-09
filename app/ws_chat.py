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

router = APIRouter()

setup_logging()
logger = logging.getLogger(__name__)

SEARCH_PATTERN = re.compile(r"\[SEARCH:\s*(.+?)\]", re.IGNORECASE)


def _extract_search_query(text: str) -> str | None:
    if not text:
        return None
    match = SEARCH_PATTERN.search(text)
    if not match:
        return None
    query = match.group(1).strip()
    return query or None


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

                # convert dict to Pydantic model
                request = GenerateRequest(**request_data)

                await websocket.send_json({"type": "status", "content": "Thinking..."})

                memories = await _recall_memories(request.prompt)
                base_system = build_system_prompt(memories=memories)
                base_system = _append_user_system_prompt(base_system, request.system_prompt)

                probe_request = GenerateRequest(**request_data)
                probe_request.system_prompt = base_system
                probe_request.max_tokens = min(request.max_tokens, 256)

                logger.info("Running search-intent probe.")
                probe_result = await engine.generate_text(probe_request)
                probe_text = probe_result.get("text", "")
                search_query = _extract_search_query(probe_text)

                if not search_query:
                    logger.info("No search requested; responding directly.")
                    await websocket.send_json({"type": "token", "content": probe_text})
                    await websocket.send_json({"type": "end", "content": ""})
                    continue

                logger.info("Search requested: %s", search_query)
                await websocket.send_json({"type": "status", "content": "Searching the web..."})

                browse_data = await search_and_browse(search_query)
                if isinstance(browse_data, dict):
                    logger.info("Search returned %s results.", len(browse_data.get("results", [])))
                else:
                    logger.warning("Search failed: %s", browse_data)
                search_context = format_search_results(browse_data)
                final_system = build_system_prompt(memories=memories, search_context=search_context)
                final_system = _append_user_system_prompt(final_system, request.system_prompt)
                request.system_prompt = final_system

                # stream tokens back
                async for token in engine.generate_stream(request):
                    await websocket.send_json({"type": "token", "content": token})

                # end of message signal
                await websocket.send_json({"type": "end", "content": ""})
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
