import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.engine import engine
from app.logging_setup import setup_logging
from app.schemas import GenerateRequest, GenerateResponse

router = APIRouter()

setup_logging()
logger = logging.getLogger(__name__)

def _model_validate(model_cls, payload: Dict[str, Any]):
    model_validate = getattr(model_cls, "model_validate", None)  # pydantic v2
    if callable(model_validate):
        return model_validate(payload)
    return model_cls(**payload)  # pydantic v1


def _model_dump(model) -> Dict[str, Any]:
    model_dump = getattr(model, "model_dump", None)  # pydantic v2
    if callable(model_dump):
        return model_dump()
    return model.dict()  # pydantic v1


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "welcome", "current_adapter": engine.adapter_id})

    while True:
        try:
            raw_message = await websocket.receive_text()
        except WebSocketDisconnect:
            return

        try:
            payload = json.loads(raw_message)
            if not isinstance(payload, dict):
                raise ValueError("Message must be a JSON object")

            request_id: Optional[str] = payload.get("request_id")
            request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else payload

            if request_payload is payload and "request_id" in request_payload:
                request_payload = dict(request_payload)
                request_payload.pop("request_id", None)

            request = _model_validate(GenerateRequest, request_payload)
            result = await engine.generate_text(request)
            response = GenerateResponse(
                text=result["text"],
                token_count=result["token_count"],
                processing_time=result["processing_time"],
            )

            message: Dict[str, Any] = {"type": "chat_response", "response": _model_dump(response)}
            if request_id is not None:
                message["request_id"] = request_id

            await websocket.send_json(message)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception as e:
            await websocket.send_json({"type": "error", "detail": str(e)})

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
