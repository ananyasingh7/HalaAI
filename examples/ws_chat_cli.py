import argparse
import asyncio
import json
import logging
import uuid

import websockets
from websockets.exceptions import InvalidStatus

from app.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def _recv_json(ws) -> dict:
    raw = await ws.recv()
    return json.loads(raw)


async def main():
    parser = argparse.ArgumentParser(description="CLI client for the websocket chat endpoints.")
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/ws/chat/v2",
        help="Websocket URL (default uses streaming/queue worker)",
    )
    parser.add_argument("--prompt", help="Single prompt to send (skips interactive mode unless --interactive)")
    parser.add_argument("--system-prompt", default=None, help="Optional system prompt")
    parser.add_argument("--max-tokens", type=int, default=1024, help="Max tokens for generation")
    parser.add_argument("--priority", type=int, default=10, help="Queue priority (lower = higher priority)")
    parser.add_argument("--interactive", action="store_true", help="Force interactive mode")
    args = parser.parse_args()

    system_prompt = args.system_prompt
    max_tokens = args.max_tokens
    interactive = args.interactive or not args.prompt

    try:
        async with websockets.connect(args.url) as ws:
            try:
                welcome = await asyncio.wait_for(_recv_json(ws), timeout=1.0)
                logger.info("Connected: %s", welcome)
            except asyncio.TimeoutError:
                logger.info("Connected.")

            async def send_prompt(prompt: str):
                request_id = str(uuid.uuid4())
                payload = {
                    "request_id": request_id,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "priority": args.priority,
                }
                if system_prompt:
                    payload["system_prompt"] = system_prompt

                await ws.send(json.dumps(payload))
                collected = []

                while True:
                    message = await _recv_json(ws)
                    msg_type = message.get("type")

                    if msg_type == "chat_response":
                        response = message.get("response", {})
                        logger.info("%s", response.get("text", ""))
                        break
                    if msg_type == "token":
                        chunk = message.get("content", "")
                        collected.append(chunk)
                        print(chunk, end="", flush=True)
                        continue
                    if msg_type == "end":
                        full_text = "".join(collected)
                        if collected:
                            print()
                        logger.info("%s", full_text)
                        break
                    if msg_type == "error":
                        logger.error("Server error: %s", message.get("detail"))
                        break

                    logger.info("%s", message)

            if args.prompt:
                await send_prompt(args.prompt)

            if not interactive:
                return

            logger.info("Interactive mode. Commands: /quit, /system <text>, /max_tokens <n>")
            while True:
                try:
                    line = input("> ").strip()
                except EOFError:
                    return

                if line in {"", "/quit", "quit", "exit"}:
                    if line in {"/quit", "quit", "exit"}:
                        return
                    continue

                if line.startswith("/system "):
                    system_prompt = line[len("/system ") :].strip() or None
                    logger.info("Updated system prompt.")
                    continue

                if line.startswith("/max_tokens "):
                    value = line[len("/max_tokens ") :].strip()
                    max_tokens = int(value)
                    logger.info("Updated max_tokens=%s", max_tokens)
                    continue

                await send_prompt(line)
    except InvalidStatus as e:
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        if status_code is not None:
            logger.critical("Server rejected WebSocket connection (HTTP %s).", status_code)
        else:
            logger.critical("Server rejected WebSocket connection.")
        logger.critical(
            "If the server logs show 'Unsupported upgrade request', the server environment is "
            "missing WebSocket support. Install deps with `python -m pip install -r requirements.txt` "
            "(or `pip install 'uvicorn[standard]'`)."
        )
        return
    except OSError as e:
        logger.critical("Connection error: %s", e)
        return


if __name__ == "__main__":
    asyncio.run(main())
