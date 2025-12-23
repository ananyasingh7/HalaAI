import argparse
import asyncio
import json
import uuid

import websockets
from websockets.exceptions import InvalidStatus


async def _recv_json(ws) -> dict:
    raw = await ws.recv()
    return json.loads(raw)


async def main():
    parser = argparse.ArgumentParser(description="CLI client for the /ws/chat websocket endpoint.")
    parser.add_argument("--url", default="ws://localhost:8000/ws/chat", help="Websocket URL")
    parser.add_argument("--prompt", help="Single prompt to send (skips interactive mode unless --interactive)")
    parser.add_argument("--system-prompt", default=None, help="Optional system prompt")
    parser.add_argument("--max-tokens", type=int, default=1024, help="Max tokens for generation")
    parser.add_argument("--interactive", action="store_true", help="Force interactive mode")
    args = parser.parse_args()

    system_prompt = args.system_prompt
    max_tokens = args.max_tokens
    interactive = args.interactive or not args.prompt

    try:
        async with websockets.connect(args.url) as ws:
            try:
                welcome = await asyncio.wait_for(_recv_json(ws), timeout=1.0)
                print(f"Connected: {welcome}")
            except asyncio.TimeoutError:
                print("Connected.")

            async def send_prompt(prompt: str):
                request_id = str(uuid.uuid4())
                payload = {"request_id": request_id, "prompt": prompt, "max_tokens": max_tokens}
                if system_prompt:
                    payload["system_prompt"] = system_prompt

                await ws.send(json.dumps(payload))
                message = await _recv_json(ws)
                if message.get("type") == "chat_response":
                    response = message.get("response", {})
                    print(response.get("text", ""))
                    return
                print(message)

            if args.prompt:
                await send_prompt(args.prompt)

            if not interactive:
                return

            print("Interactive mode. Commands: /quit, /system <text>, /max_tokens <n>")
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
                    print("Updated system prompt.")
                    continue

                if line.startswith("/max_tokens "):
                    value = line[len("/max_tokens ") :].strip()
                    max_tokens = int(value)
                    print(f"Updated max_tokens={max_tokens}")
                    continue

                await send_prompt(line)
    except InvalidStatus as e:
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        if status_code is not None:
            print(f"Server rejected WebSocket connection (HTTP {status_code}).")
        else:
            print("Server rejected WebSocket connection.")
        print(
            "If the server logs show 'Unsupported upgrade request', the server environment is "
            "missing WebSocket support. Install deps with `python -m pip install -r requirements.txt` "
            "(or `pip install 'uvicorn[standard]'`)."
        )
        return
    except OSError as e:
        print(f"Connection error: {e}")
        return


if __name__ == "__main__":
    asyncio.run(main())
