# HalaAI Integration (External Repos)

This document explains how to connect to HalaAI from another repo or workspace.

## Endpoints

- WebSocket (streaming): `ws://localhost:8000/ws/chat/v2`
- HTTP (blocking): `http://localhost:8000/chat`
- Data APIs:
  - `GET /data/sessions`
  - `GET /data/session?session_id=<uuid>`
  - `GET /data/summaries`
  - `DELETE /data/session?session_id=<uuid>`
  - `POST /data/vector/search`

## WebSocket Protocol (Streaming)

The WebSocket is the primary integration path. It supports session tracking, streaming tokens, and deep search/expansion behind the scenes.

### 1) Start a session

Send a session start event when a new chat begins:

```json
{ "type": "session_start", "session_id": "UUID" }
```

### 2) Send a prompt

Each message should include the same `session_id` so chat history is persisted:

```json
{
  "prompt": "Who won the Super Bowl?",
  "max_tokens": 512,
  "session_id": "UUID",
  "include_history": true,
  "history_window": 12,
  "system_prompt": "Optional system override"
}
```

Optional fields:
- `priority` (lower = higher priority; defaults to standard)
- `system_prompt` (appends to the base system prompt)
- `include_history` (if false, history is still stored but NOT injected into the prompt)
- `history_window` (number of most recent messages to inject when `include_history=true`)

### 3) Receive messages

The server streams JSON events:

- `{"type":"status","content":"Thinking..."}`
- `{"type":"token","content":"..."}`
- `{"type":"end","content":""}`
- `{"type":"error","detail":"..."}`

### 4) End a session

When the UI or agent closes, signal session end so the server can summarise:

```json
{ "type": "session_end", "session_id": "UUID" }
```

## WebSocket cURL Example

`curl` doesn’t speak WebSocket natively, so use `wscat`:

```bash
npm i -g wscat
wscat -c ws://localhost:8000/ws/chat/v2
```

Then send:

```json
{"type":"session_start","session_id":"11111111-1111-1111-1111-111111111111"}
```

```json
{"prompt":"Who won the Super Bowl?","max_tokens":256,"session_id":"11111111-1111-1111-1111-111111111111"}
```

```json
{"type":"session_end","session_id":"11111111-1111-1111-1111-111111111111"}
```

## HTTP API (Blocking)

This is a single-response endpoint. Note: it does **not** include session history, memory recall, or deep search.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hello","max_tokens":256,"priority":10}'
```

## Data APIs (cURL)

List sessions:

```bash
curl -s http://localhost:8000/data/sessions
```

Fetch one session:

```bash
curl -s "http://localhost:8000/data/session?session_id=YOUR_UUID"
```

List summaries:

```bash
curl -s http://localhost:8000/data/summaries
```

Delete a session:

```bash
curl -X DELETE "http://localhost:8000/data/session?session_id=YOUR_UUID"
```

Vector search:

```bash
curl -X POST http://localhost:8000/data/vector/search \
  -H "Content-Type: application/json" \
  -d '{"query":"recent chat about football","n_results":5,"threshold":1.2,"where":{"source":"chat_summary"}}'
```

## Environment Variables

- `HALA_WS_URL` (client-side): set WebSocket URL (e.g., `ws://localhost:8000/ws/chat/v2`)
- `HALA_HISTORY_DB_URL` (server-side): Postgres connection for sessions

## Notes

- The server automatically handles:
  - Web search + scraping when the model emits `[SEARCH: <query>]`
  - Transcript expansion when the model emits `[EXPAND: <session_uuid>]`
- If you need guaranteed context, include a `system_prompt` or use the session APIs to fetch history.
