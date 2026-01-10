import json
import os
import asyncio
import uuid
from urllib.parse import urlparse

import chainlit as cl
import websockets
from websockets.exceptions import InvalidStatus

WS_URL = os.getenv("HALA_WS_URL", "ws://localhost:8000/ws/chat/v2")


def _configure_engineio_limits() -> None:
    # Avoid Engine.IO rejecting larger polling payloads under load.
    try:
        from engineio.payload import Payload
    except Exception:
        return

    max_packets = int(os.getenv("ENGINEIO_MAX_DECODE_PACKETS", "128"))
    Payload.max_decode_packets = max_packets


_configure_engineio_limits()


def _url_port(url: str) -> int | None:
    parsed = urlparse(url)
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "wss":
        return 443
    if parsed.scheme == "ws":
        return 80
    return None


def _port_conflict_hint(ws_url: str) -> str | None:
    chainlit_port = int(os.getenv("CHAINLIT_PORT", "8000"))
    ws_port = _url_port(ws_url)
    if ws_port == chainlit_port:
        return (
            "Port conflict detected: Chainlit and the LLM server are using the same port. "
            "Run Chainlit on 8001: `CHAINLIT_PORT=8001 python3 -m chainlit run app.py -w`."
        )
    return None


@cl.on_chat_start
async def on_chat_start():
    session_id = str(uuid.uuid4())
    cl.user_session.set("session_id", session_id)

    settings = await cl.ChatSettings(
        [
            cl.input_widget.TextInput(
                id="system_prompt",
                label="System prompt",
                placeholder="(optional)",
                initial=os.getenv("HALA_SYSTEM_PROMPT", ""),
            ),
            cl.input_widget.Slider(
                id="max_tokens",
                label="Max tokens",
                initial=int(os.getenv("HALA_MAX_TOKENS", "1024")),
                min=32,
                max=4096,
                step=32,
            ),
        ]
    ).send()

    await on_settings_update(settings)

    status = f"WS: `{WS_URL}`"
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "session_start", "session_id": session_id}))
            try:
                await ws.recv()
            except Exception:
                pass
        status += " (ok)"
    except InvalidStatus as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        status += f" (rejected: HTTP {code or '???'})"
    except Exception:
        status += " (not reachable yet)"

    hint = _port_conflict_hint(WS_URL)
    if hint:
        status += f"\n\n{hint}"

    await cl.Message(content=f"Ready. {status}").send()


@cl.on_settings_update
async def on_settings_update(settings):
    cl.user_session.set("system_prompt", (settings.get("system_prompt") or "").strip() or None)
    cl.user_session.set("max_tokens", int(settings.get("max_tokens") or 1024))


@cl.on_message
async def on_message(message: cl.Message):
    system_prompt = cl.user_session.get("system_prompt")
    max_tokens = cl.user_session.get("max_tokens") or 1024
    session_id = cl.user_session.get("session_id")

    thinking = cl.Message(content="...")
    await thinking.send()

    try:
        async with websockets.connect(WS_URL) as ws:
            payload = {
                "prompt": message.content,
                "max_tokens": int(max_tokens),
                "session_id": session_id,
            }
            if system_prompt:
                payload["system_prompt"] = system_prompt

            await ws.send(json.dumps(payload))
            assembled = ""
            last_update = 0.0

            while True:
                server_msg = json.loads(await ws.recv())
                msg_type = server_msg.get("type")

                if msg_type == "status":
                    status_text = server_msg.get("content") or server_msg.get("detail") or "Thinking..."
                    if not assembled:
                        thinking.content = status_text
                        await thinking.update()
                    continue

                if msg_type == "token":
                    assembled += server_msg.get("content") or ""
                    now = asyncio.get_running_loop().time()
                    if (now - last_update) >= 0.08:
                        thinking.content = assembled or "..."
                        await thinking.update()
                        last_update = now
                    continue

                if msg_type == "end":
                    break

                if msg_type == "error":
                    assembled = f"Error: {server_msg.get('detail') or server_msg}"
                    break

                # Unknown message type; surface it and stop.
                assembled = f"Unexpected message: {server_msg}"
                break

        thinking.content = assembled
        await thinking.update()
    except InvalidStatus as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        hint = _port_conflict_hint(WS_URL)
        details = hint or "Make sure `python3 run_server.py` is running and `HALA_WS_URL` points to it."
        thinking.content = f"Connection error: server rejected WebSocket connection (HTTP {code or '???'}).\n{details}"
        await thinking.update()
    except Exception as e:
        thinking.content = f"Connection error: {e}"
        await thinking.update()


@cl.on_chat_end
async def on_chat_end():
    session_id = cl.user_session.get("session_id")
    if not session_id:
        return
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "session_end", "session_id": session_id}))
            try:
                await ws.recv()
            except Exception:
                pass
    except Exception:
        pass
