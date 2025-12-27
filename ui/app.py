import json
import os
import asyncio
from urllib.parse import urlparse
from urllib.parse import urlunparse

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


def _with_path(url: str, path: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=path))


def _port_conflict_hint(ws_url: str) -> str | None:
    chainlit_port = int(os.getenv("CHAINLIT_PORT", "8000"))
    ws_port = _url_port(ws_url)
    if ws_port == chainlit_port:
        return (
            "Port conflict detected: Chainlit and the LLM server are using the same port. "
            "Run Chainlit on 8001: `CHAINLIT_PORT=8001 python3 -m chainlit run app.py -w`."
        )
    return None


async def _diagnose_403(ws_url: str) -> str | None:
    """
    Starlette commonly returns HTTP 403 during websocket handshake when no websocket route matches.
    Try v1 as a quick sanity check to help the user fix ports/restarts.
    """
    if not ws_url.endswith("/ws/chat/v2"):
        return None

    v1_url = _with_path(ws_url, "/ws/chat")
    try:
        async with websockets.connect(v1_url) as ws:
            # v1 sends a welcome message; wait briefly to confirm.
            await asyncio.wait_for(ws.recv(), timeout=1.0)
        return (
            f"`{ws_url}` is being rejected (403) but `{v1_url}` works. "
            "This usually means the server you restarted doesn't have `/ws/chat/v2` registered yet. "
            "Stop and restart `python3 run_server.py` after updating `app/ws_chat.py`."
        )
    except Exception:
        return (
            f"`{ws_url}` is being rejected (403). Also couldn't confirm `{v1_url}`. "
            "Double-check `HALA_WS_URL` points to the FastAPI server (not Chainlit) and the correct port."
        )


@cl.on_chat_start
async def on_chat_start():
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
            # v2 does not send an initial "welcome" message. Connecting successfully is enough.
            await ws.close()
        status += " (ok)"
    except InvalidStatus as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        status += f" (rejected: HTTP {code or '???'})"
        if (code or 0) == 403:
            diag = await _diagnose_403(WS_URL)
            if diag:
                status += f"\n\n{diag}"
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

    thinking = cl.Message(content="...")
    await thinking.send()

    try:
        async with websockets.connect(WS_URL) as ws:
            payload = {"prompt": message.content, "max_tokens": int(max_tokens)}
            if system_prompt:
                payload["system_prompt"] = system_prompt

            await ws.send(json.dumps(payload))
            assembled = ""
            last_update = 0.0

            while True:
                server_msg = json.loads(await ws.recv())
                msg_type = server_msg.get("type")

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
        if (code or 0) == 403:
            diag = await _diagnose_403(WS_URL)
            if diag:
                details = diag
        thinking.content = f"Connection error: server rejected WebSocket connection (HTTP {code or '???'}).\n{details}"
        await thinking.update()
    except Exception as e:
        thinking.content = f"Connection error: {e}"
        await thinking.update()
