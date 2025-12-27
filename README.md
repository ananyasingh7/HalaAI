# HalaAI

HalaAI is a local LLM hub that keeps a high-performance model running on a Mac Studio (Apple Silicon) and lets multiple apps tap into it on demand. The server stays alive, manages GPU access, and exposes HTTP and WebSocket APIs for low-latency chat, streaming, and agent workflows.

## Vision

Build a private, always-on "LLM operating system" where one central engine powers many spokes: UIs, agents, and analysis tools. The heavy model loads once, stays warm, and swaps specialized LoRA adapters without reloading the base weights.

## Tech Stack

- Hardware: Mac Studio M4 (unified memory).
- Inference: MLX via `mlx-lm` for bare-metal Apple Silicon performance.
- Server: FastAPI with HTTP + WebSocket endpoints.
- Orchestration: LangChain agents via a custom local LLM wrapper.
- UI: Chainlit web chat.
- Data: SQLModel + SQLite logging; Pandas used for metrics analysis.

## Model Setup

- Base model: `mlx-community/Qwen2.5-14B-Instruct-4bit`.
- Quantization: 4-bit to fit in local memory.
- Adapters: LoRA personalities stored in `adapters/` and hot-swapped at runtime.

## Architecture

```
Spokes (UI, agents, tools)
        |
        v
FastAPI server (HTTP + WebSocket)
        |
        v
ModelEngine singleton (MLX)
        |
        +--> LoRA adapters (hot swap)
        +--> SQLite logs + hardware monitor
```

Key behaviors are implemented in:
- `app/engine.py` for the singleton engine, adapter swapping, and GPU lock.
- `app/ws_chat.py` for streaming WebSocket responses.
- `app/database.py` for inference logs.
- `app/monitor.py` for hardware stats polling.

## Quickstart

1) Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2) Start the FastAPI server:

```bash
python3 run_server.py
```

3) (Optional) Start the Chainlit UI on a different port:

```bash
cd ui
CHAINLIT_PORT=8001 python3 -m chainlit run app.py -w
```

If your server runs elsewhere, set:

```bash
HALA_WS_URL=ws://localhost:8000/ws/chat/v2
```

## API Overview

HTTP:
- `GET /` health check (returns current adapter).
- `POST /chat` blocking generation.
- `POST /adapters/load` hot-swap LoRA adapters.

WebSocket:
- `ws://localhost:8000/ws/chat` for JSON request/response.
- `ws://localhost:8000/ws/chat/v2` for streaming tokens.

Example request:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hello","max_tokens":256}'
```

## Adapters

- Adapters live in `adapters/`.
- Use `adapter_name="default"` to load a single adapter stored directly in `adapters/`.
- Use `adapter_name="<folder>"` to load a named adapter in `adapters/<folder>/`.
- Use `adapter_name="base"` or `adapter_name="none"` to unload to the base model.

Example:

```bash
curl -X POST http://localhost:8000/adapters/load \
  -H "Content-Type: application/json" \
  -d '{"adapter_name":"default"}'
```

## Performance and Evals

### Performance

- Avg ~29.8 tokens/sec with peaks around ~38 t/s for the 14B model.
- Roughly 4x human reading speed (~5-8 tokens/sec).
- Total time vs tokens-out is linear, indicating stable throughput as responses get longer.

![Inference stats](perfomance/inference_stats_12-26-2025.png)

### Evals

- Report: `evals/results/eval_report_golden_general_20251223_170911.md`
- Dataset: `evals/datasets/golden_general.jsonl` (max tokens: 200)
- Base model: 41/50 keyword hits (82.0%)
- Tuned adapter: 39/50 keyword hits (78.0%)

## Streaming UI (Chainlit)

See `ui/chainlit.md` for detailed UI setup. The UI connects to `ws://localhost:8000/ws/chat/v2` and streams tokens into the chat pane.

## LangChain Integration

Use `examples/langchain/HalaLLM.py` to plug the local hub into LangChain as a custom LLM provider. The sports agent example is in `examples/langchain/sports_agent.py`.

## Logging and Monitoring

- Logs are stored in `inference_logs.db` via SQLModel.
- Hardware stats are polled in `app/monitor.py`.
- For GPU stats on macOS, install macmon:

```bash
brew install vladkens/tap/macmon
```

## Evals

Lightweight evaluation scripts live in `evals/`.

```bash
python evals/runners.py
python evals/runners.py --dataset evals/datasets/golden_general.jsonl
```

## Project Layout

- `app/` FastAPI server, engine, WebSocket handlers, logging, monitoring.
- `ui/` Chainlit chat client.
- `examples/` API, WebSocket, and LangChain integration samples.
- `adapters/` LoRA adapter weights and config.
- `evals/` evaluation scripts and reports.
- `data/` fine-tuning datasets.
- `perfomance/` performance logs and plots.

## Performance Notes

Local tests on the Mac Studio M4 show:
- ~30 tokens/sec streaming throughput.
- Adapter fine-tuning retained personal facts without degrading general reasoning in the "golden dataset" checks.
