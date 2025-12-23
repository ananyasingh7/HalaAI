# Hala UI

Lightweight chat UI that sends prompts to your running FastAPI websocket.

## Run

1) Start the LLM server:

`python3 run_server.py`

2) Start Chainlit on a different port (FastAPI already uses `:8000`):

`cd ui && CHAINLIT_PORT=8001 python3 -m chainlit run app.py -w`

If your server runs elsewhere, set:

`HALA_WS_URL=ws://localhost:8000/ws/chat/v2`
