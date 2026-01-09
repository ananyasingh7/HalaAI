# HalaAI Architecture Flow

This document summarizes how requests move through HalaAI from client to GPU and back.

## High-Level Runtime

```
Client/UI/Tools
    |
    v
FastAPI app (app/main.py)
    |
    +--> HTTP /chat (blocking) -> engine.generate_text
    |
    +--> WebSocket /ws/chat/v2 (streaming)
           -> memory recall (core/memory.py)
           -> search intent probe (app/prompts.py)
           -> Brave deep search + browse (core/search/brave_browse.py)
           -> engine.generate_stream (queue + GPU worker)
```

## Connection Diagram (Where `main.py` Fits)

```
run_server.py
    |
    v
app/main.py  ->  FastAPI app instance
    |
    +--> include_router(app/ws_chat.py)  ->  registers /ws/chat/v2
    |
    +--> defines HTTP routes (/chat, /adapters/load)
    |
    +--> startup/shutdown hooks (start queue worker + monitor)
```

## Entry Points

- `run_server.py` starts Uvicorn with `app.main:app`.
- `app/main.py` registers routes and starts the engine background tasks on startup.

## WebSocket Streaming Flow (`/ws/chat/v2`)

1) Client sends a JSON payload with `prompt`, `max_tokens`, and optional `system_prompt` + `priority`.
2) `app/ws_chat.py` emits a `{"type": "status"}` message (e.g., "Thinking...").
3) The API layer calls `core.memory.recall(prompt)` and builds a base system prompt via `app/prompts.py`.
4) A short "search-intent probe" pass is run to detect a `[SEARCH: ...]` command.
5) If search is requested, `core/search/brave_browse.py` performs Brave search + page scraping.
6) Search results are formatted via `app/prompts.py` and injected into the system prompt.
7) `engine.generate_stream(request)` enqueues a job in `app/queue.py`.
8) The GPU worker (`ModelEngine._worker_loop` in `app/engine.py`) consumes the job, runs
   `stream_generate`, and pushes tokens onto the response queue.
9) `app/ws_chat.py` streams tokens back as `{"type": "token"}` messages and finishes with
   `{"type": "end"}`.
10) Inference stats are logged via `app/database.py`, and hardware metrics come from `app/monitor.py`.

## HTTP Blocking Flow (`/chat`)

- `app/main.py` receives a POST request and calls `engine.generate_text`.
- This path runs inference directly under the engine lock (no queue, no streaming).
- Memory recall and deep search are not applied here; they are only done in the WebSocket API layer.

## Memory (RAG) Flow

- Storage: `core/memory.py` uses ChromaDB with a persistent path at `data/vector_db/`.
- Ingestion: `core/teach.py` is the manual entrypoint for facts (chat history is not auto-ingested).
- Recall: `core/memory.py` embeds the query, pulls top matches, and filters by distance threshold.

## Queue + GPU Worker

- `app/queue.py` is a priority queue (lower number = higher priority).
- `engine.start_background_tasks()` spins up:
  - a queue worker to run GPU inference, and
  - a queue monitor to log depth + latency.
- `engine.generate_stream` enqueues a job and yields tokens from a per-request response queue.

## Adapters (LoRA)

- `app/engine.py` loads LoRA adapters from `adapters/`.
- `/adapters/load` swaps adapters without reloading the base model.

## UI Flow (Chainlit)

- `ui/app.py` connects to `/ws/chat/v2`, displays status messages, and streams tokens.
- `ui/chainlit.md` documents the UI startup steps.

## Examples

- `examples/ws_chat_cli.py` streams from `/ws/chat/v2`.
- `examples/basic_api.py` uses the blocking HTTP `/chat` endpoint.
- `examples/langchain/HalaLLM.py` wraps the HTTP `/chat` endpoint for LangChain.

## Data + Artifacts

- `data/vector_db/`: ChromaDB persistent store for memory.
- `inference_logs.db`: inference logs via SQLModel.
- `perfomance/`: performance plots and logs.
- `evals/`: evaluation datasets and reports.
