import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.engine import engine
from app.logging_setup import setup_logging
from app.schemas import GenerateRequest
from core import memory

router = APIRouter()

setup_logging()
logger = logging.getLogger(__name__)

def _build_memory_context(memories) -> str:
    return "\n".join(f"- {fact}" for fact in memories)


async def _apply_memory_context(request: GenerateRequest, websocket: WebSocket) -> None:
    await websocket.send_json({"type": "status", "content": "Thinking..."})
    try:
        memories = memory.recall(request.prompt)
    except Exception:
        logger.exception("Memory recall failed; continuing without context.")
        return

    if not memories:
        return

    context_block = _build_memory_context(memories)
    original_system = request.system_prompt or ""
    request.system_prompt = (
        f"{original_system}\n\n"
        f"## CONTEXT FROM MEMORY:\n"
        f"{context_block}\n\n"
        f"INSTRUCTION: The above memory may or may not be relevant. "
        f"If it helps answer the user, use it. "
        f"If it is irrelevant to the specific question (e.g. asking for live status vs static fact), IGNORE IT."
    )


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

                await _apply_memory_context(request, websocket)

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
