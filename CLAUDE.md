# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

HalaAI is a local LLM server running Qwen3-30B-A3B (4-bit, MLX) on a Mac Studio M4. It exposes HTTP and WebSocket APIs for streaming chat, with a priority queue, session persistence (Postgres + Chroma), and Brave-powered deep search.

## Commands

```bash
# Install dependencies
python3 -m pip install -r requirements.txt

# Start the server (port 8000)
python3 run_server.py

# Start the Chainlit UI (port 8001)
cd ui && CHAINLIT_PORT=8001 python3 -m chainlit run app.py -w

# Run all tests
python -m unittest discover -s tests -p "test_*.py"

# Run a single test file
python -m unittest tests/test_queue.py

# Run evals
python evals/runners.py
python evals/runners.py --dataset evals/datasets/golden_general.jsonl

# Wipe Postgres sessions + Chroma vector DB
python3 data/reset_datastores.py

# Debug server with VS Code (attach via .vscode/launch.json)
python -m debugpy --listen 5678 --wait-for-client run_server.py
```

## Architecture

```
Spokes (UI, agents, external clients)
          |
          v
  FastAPI (HTTP + WebSocket)
          |
          v
  ModelEngine singleton (MLX)   ← GPU lock prevents concurrent access
          |
    +---------+-----------+-----------+
    |         |           |           |
LoRA adapt  Queue     Session DB    SQLite logs
(hot-swap)  (min-heap) Postgres +   (inference
             w/ aging   Chroma       metrics)
```

**Request flow (WebSocket):**
1. Client sends `session_start` → `app/ws_chat.py` initialises session in Postgres
2. Each message: probe for `[SEARCH: ...]` / `[EXPAND: ...]` patterns
3. Build system prompt: `app/prompts.py` assembles persona + tools + search context + memory recall
4. Enqueue to `app/queue.py` (priority min-heap) → `app/engine.py` worker dequeues and streams MLX tokens
5. `<think>...</think>` spans from Qwen3 are stripped before tokens reach the client
6. On `session_end` or 10-min idle: `app/session_manager.py` generates title + summary → embedded into Chroma

## Key Files

| File | Role |
|------|------|
| `app/engine.py` | ModelEngine singleton — loads model, GPU lock, adapter hot-swap, `_worker_loop`, thinking filter |
| `app/ws_chat.py` | WebSocket handler — search/expand probes, memory recall, prompt assembly, streaming |
| `app/prompts.py` | System prompt builder — loads `prompts/*.md`, injects search results, history, summaries |
| `app/queue.py` | Priority min-heap queue with starvation prevention (aging every 60s) |
| `app/session_manager.py` | Postgres session CRUD, auto-summarisation, idle sweeper |
| `app/monitor.py` | Hardware stats via `macmon` (GPU) + `psutil` (CPU/RAM) |
| `app/database.py` | SQLite inference log (`InferenceLog` model) |
| `core/search/brave_browse.py` | Brave API + Trafilatura scraping pipeline |
| `data/sql/database.py` | SQLModel Postgres schema (`sessions` table with JSONB history) |
| `data/sql/expander.py` | Fetches full transcript for `[EXPAND: <uuid>]` |

## Prompt System

System prompts are Markdown files loaded at runtime from `prompts/`:
- `SYSTEM.md` — Core persona and behavioural rules
- `AGENT.md` — Tool protocol (when/how to emit `[SEARCH: ...]`, `[EXPAND: ...]`)
- `PROJECT.md` — Project context
- `USER.md` — User profile

`app/prompts.py` assembles them with injected context (search results, memory, history, datetime).

## Priority Queue

- Lower number = higher priority. UI requests use `0`, standard `10`, background `20`.
- Configured in `config/queue.yaml`.
- Starvation prevention: items age up in priority every 60 seconds.
- Client payloads include optional `priority` field.

## LoRA Adapter Swapping

- Adapters stored in `adapters/` (not committed — create locally).
- `adapter_name="default"` → `adapters/` root; `adapter_name="<name>"` → `adapters/<name>/`.
- `adapter_name="base"` unloads to base model.
- Qwen2.5 adapters are **not** compatible with Qwen3.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HALA_WS_URL` | `ws://localhost:8000/ws/chat/v2` | WebSocket endpoint for UI |
| `HALA_HISTORY_DB_URL` | SQLite fallback | Postgres DSN for session history |
| `BRAVE_API_KEY` | — | Required for deep search |

## Brave Search Quota

Enforced in `core/search/brave_search.py`. Config in `config/brave_search_limits.json` (default 1000/month). Only HTTP 200 responses count against quota. Auto-blocklist for repeatedly failing domains in `config/search_blocklist_failures.json`.

## Testing Notes

Tests in `tests/` use `unittest`. `conftest.py` adds the repo root to `sys.path`. Tests that hit Postgres or Chroma may require running services. The queue, prompt, and monitor tests are purely unit-level with no external deps.
