import argparse
import asyncio
import json
import sqlite3
import statistics
import time
from pathlib import Path

import websockets


DEFAULT_URL = "ws://localhost:8000/ws/chat/v2"
BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = str(BASE_DIR / "inference_logs.db")


def _connect_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection, db_path: str) -> None:
    cur = conn.execute(
        "select name from sqlite_master where type='table' and name='inferencelog'"
    )
    if cur.fetchone() is None:
        raise RuntimeError(
            "Missing table inferencelog in {db}. "
            "Start the server once to initialize the DB, or from the repo root run: "
            "python -c \"from app.database import init_db; init_db()\" "
            "or pass --db with the correct path.".format(db=db_path)
        )


def _get_last_id(conn: sqlite3.Connection) -> int:
    cur = conn.execute("select max(id) as max_id from inferencelog")
    row = cur.fetchone()
    return int(row["max_id"] or 0)


def _wait_for_new_row(conn: sqlite3.Connection, last_id: int, timeout: float) -> sqlite3.Row:
    deadline = time.time() + timeout
    while time.time() < deadline:
        cur = conn.execute(
            "select id, tokens_in, tokens_out, total_time_sec, tokens_per_sec "
            "from inferencelog where id > ? order by id desc limit 1",
            (last_id,),
        )
        row = cur.fetchone()
        if row:
            return row
        time.sleep(0.2)
    raise TimeoutError("Timed out waiting for inference log row")


def _wait_for_rows(conn: sqlite3.Connection, last_id: int, expected: int, timeout: float) -> list[sqlite3.Row]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        cur = conn.execute(
            "select id, tokens_in, tokens_out, total_time_sec, tokens_per_sec "
            "from inferencelog where id > ? order by id",
            (last_id,),
        )
        rows = cur.fetchall()
        if len(rows) >= expected:
            return rows
        time.sleep(0.2)
    raise TimeoutError("Timed out waiting for inference log rows")


PROMPT_PRESETS = {
    "lines": "Write the number 1 on each line, repeating until you reach 20000 lines. Do not add any other text.",
    "numbers": "Output a list of numbers from 1 to 20000, one per line. Do not stop early.",
    "lorem": "Write a long, continuous paragraph of lorem ipsum without headings or lists. Keep going until you reach the limit.",
}


def _build_prompt(args: argparse.Namespace, words: int) -> str:
    if args.prompt:
        return args.prompt
    if args.prompt_preset:
        return PROMPT_PRESETS[args.prompt_preset]
    return ((args.prompt_token + " ") * words).strip()


async def _ws_request(
    url: str,
    prompt: str,
    max_tokens: int,
    priority: int,
    system_prompt: str | None,
    timeout: float,
    ping_interval: float | None,
    ping_timeout: float | None,
) -> None:
    async with websockets.connect(
        url,
        max_size=None,
        ping_interval=ping_interval,
        ping_timeout=ping_timeout,
    ) as ws:
        payload = {"prompt": prompt, "max_tokens": max_tokens, "priority": priority}
        if system_prompt:
            payload["system_prompt"] = system_prompt
        await ws.send(json.dumps(payload))
        start = time.time()
        while True:
            if time.time() - start > timeout:
                raise TimeoutError("WebSocket request timed out")
            msg = json.loads(await ws.recv())
            msg_type = msg.get("type")
            if msg_type == "token":
                continue
            if msg_type == "end":
                return
            if msg_type == "error":
                raise RuntimeError(msg.get("detail", "Server error"))


async def _context_sweep(args: argparse.Namespace) -> None:
    conn = _connect_db(args.db)
    _ensure_table(conn, args.db)
    last_id = _get_last_id(conn)

    n = args.context_start
    while n <= args.context_max:
        prompt = (args.prompt_token + " ") * n
        prompt = prompt.strip()
        print(f"context_sweep: words={n} max_tokens=1")
        try:
            await _ws_request(
                args.url,
                prompt,
                max_tokens=1,
                priority=args.priority,
                system_prompt=args.system_prompt,
                timeout=args.timeout,
                ping_interval=args.ping_interval,
                ping_timeout=args.ping_timeout,
            )
        except Exception as exc:
            print(f"  failed at words={n}: {exc}")
            break

        row = _wait_for_new_row(conn, last_id, args.log_timeout)
        last_id = row["id"]
        print(
            "  tokens_in={tokens_in} tokens_out={tokens_out} tps={tps:.2f} time={time_s:.2f}s".format(
                tokens_in=row["tokens_in"],
                tokens_out=row["tokens_out"],
                tps=row["tokens_per_sec"],
                time_s=row["total_time_sec"],
            )
        )
        n *= args.context_step


async def _output_sweep(args: argparse.Namespace) -> None:
    conn = _connect_db(args.db)
    _ensure_table(conn, args.db)
    last_id = _get_last_id(conn)

    n = args.output_start
    prompt = _build_prompt(args, args.prompt_words)

    while n <= args.output_max:
        if args.prompt:
            print(f"output_sweep: max_tokens={n} prompt=custom")
        elif args.prompt_preset:
            print(f"output_sweep: max_tokens={n} prompt_preset={args.prompt_preset}")
        else:
            print(f"output_sweep: max_tokens={n} prompt_words={args.prompt_words}")
        try:
            await _ws_request(
                args.url,
                prompt,
                max_tokens=n,
                priority=args.priority,
                system_prompt=args.system_prompt,
                timeout=args.timeout,
                ping_interval=args.ping_interval,
                ping_timeout=args.ping_timeout,
            )
        except Exception as exc:
            print(f"  failed at max_tokens={n}: {exc}")
            break

        row = _wait_for_new_row(conn, last_id, args.log_timeout)
        last_id = row["id"]
        print(
            "  tokens_in={tokens_in} tokens_out={tokens_out} tps={tps:.2f} time={time_s:.2f}s".format(
                tokens_in=row["tokens_in"],
                tokens_out=row["tokens_out"],
                tps=row["tokens_per_sec"],
                time_s=row["total_time_sec"],
            )
        )
        n *= args.output_step


async def _concurrency_test(args: argparse.Namespace) -> None:
    conn = _connect_db(args.db)
    _ensure_table(conn, args.db)
    last_id = _get_last_id(conn)

    prompt = _build_prompt(args, args.prompt_words)

    if args.prompt:
        print(f"concurrency_test: clients={args.clients} max_tokens={args.concurrency_tokens} prompt=custom")
    elif args.prompt_preset:
        print(f"concurrency_test: clients={args.clients} max_tokens={args.concurrency_tokens} prompt_preset={args.prompt_preset}")
    else:
        print(f"concurrency_test: clients={args.clients} max_tokens={args.concurrency_tokens}")
    start = time.time()
    await asyncio.gather(
        *[
            _ws_request(
                args.url,
                prompt,
                max_tokens=args.concurrency_tokens,
                priority=args.priority,
                system_prompt=args.system_prompt,
                timeout=args.timeout,
                ping_interval=args.ping_interval,
                ping_timeout=args.ping_timeout,
            )
            for _ in range(args.clients)
        ]
    )
    wall_time = time.time() - start

    rows = _wait_for_rows(conn, last_id, args.clients, args.log_timeout)
    tokens_out = [row["tokens_out"] for row in rows]
    tps = [row["tokens_per_sec"] for row in rows]
    total_out = sum(tokens_out)
    avg_tps = statistics.mean(tps) if tps else 0.0
    print(
        "  completed={count} total_tokens_out={total} wall_time={wall:.2f}s avg_tps={avg:.2f} max_tps={mx:.2f} min_tps={mn:.2f}".format(
            count=len(rows),
            total=total_out,
            wall=wall_time,
            avg=avg_tps,
            mx=max(tps) if tps else 0.0,
            mn=min(tps) if tps else 0.0,
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stress test HalaAI over WebSocket and read stats from SQLite logs.")
    parser.add_argument("--url", default=DEFAULT_URL, help="WebSocket URL")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to inference_logs.db")
    parser.add_argument("--system-prompt", default=None, help="Optional system prompt")
    parser.add_argument("--priority", type=int, default=10, help="Queue priority (lower = higher priority)")
    parser.add_argument("--timeout", type=float, default=300.0, help="Per-request timeout in seconds")
    parser.add_argument("--log-timeout", type=float, default=30.0, help="Timeout waiting for log rows")
    parser.add_argument("--ping-interval", type=float, default=20.0, help="WebSocket ping interval (seconds)")
    parser.add_argument("--ping-timeout", type=float, default=20.0, help="WebSocket ping timeout (seconds)")
    parser.add_argument("--no-ping", action="store_true", help="Disable WebSocket keepalive pings")

    parser.add_argument("--mode", choices=["context", "output", "concurrency", "all"], default="all")

    parser.add_argument("--prompt-token", default="hello", help="Token used to build prompts")
    parser.add_argument("--prompt-words", type=int, default=64, help="Prompt size for output/concurrency tests")
    parser.add_argument("--prompt", default=None, help="Override prompt for output/concurrency tests")
    parser.add_argument(
        "--prompt-preset",
        choices=sorted(PROMPT_PRESETS.keys()),
        default=None,
        help="Use a built-in prompt preset for long outputs (ignored if --prompt is set)",
    )

    parser.add_argument("--context-start", type=int, default=128, help="Starting word count for context sweep")
    parser.add_argument("--context-max", type=int, default=4096, help="Max word count for context sweep")
    parser.add_argument("--context-step", type=int, default=2, help="Multiplier per step for context sweep")

    parser.add_argument("--output-start", type=int, default=512, help="Starting max_tokens for output sweep")
    parser.add_argument("--output-max", type=int, default=4096, help="Max max_tokens for output sweep")
    parser.add_argument("--output-step", type=int, default=2, help="Multiplier per step for output sweep")

    parser.add_argument("--clients", type=int, default=4, help="Concurrent clients for queue stress")
    parser.add_argument("--concurrency-tokens", type=int, default=1024, help="max_tokens per client")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.context_step < 2 or args.output_step < 2:
        raise SystemExit("context-step and output-step should be >= 2")
    if args.no_ping:
        args.ping_interval = None
        args.ping_timeout = None

    async def runner() -> None:
        if args.mode in {"context", "all"}:
            await _context_sweep(args)
        if args.mode in {"output", "all"}:
            await _output_sweep(args)
        if args.mode in {"concurrency", "all"}:
            await _concurrency_test(args)

    asyncio.run(runner())


if __name__ == "__main__":
    main()
