# Stress Test Notes (Current)

This document reflects the current stress harness in `performance/stress_test.py`.

## What Changed

- Added memory-awareness via `GET /metrics/memory`.
- Added per-run artifact export (JSON + CSV) under `performance/results/`.
- Added estimated generation cap reporting based on `engine_memory.max_kv_size` and `prompt_token_reserve`.
- Kept the same three stress modes: `context`, `output`, `concurrency`.

## Standard Runs

Context sweep:

```bash
python performance/stress_test.py --mode context --context-max 16384 --no-ping --run-label context_sweep
```

Output sweep:

```bash
python performance/stress_test.py --mode output --output-max 8192 --prompt-preset lines --no-ping --run-label output_sweep
```

Concurrency sweep:

```bash
python performance/stress_test.py --mode concurrency --clients 6 --concurrency-tokens 768 --run-label concurrency_sweep
```

Combined run:

```bash
python performance/stress_test.py --mode all --context-max 8192 --output-max 4096 --clients 4 --run-label full_suite
```

## Outputs

Each run writes:

- `performance/results/stress_<timestamp>_<label>.json`
- `performance/results/stress_<timestamp>_<label>.csv`

These include:

- Request shape (`mode`, requested token counts, client count)
- Logged inference stats (`tokens_in`, `tokens_out`, `tokens_per_sec`, `total_time_sec`)
- Memory snapshot fields when metrics are enabled (`system_ram_gb`, `process_ram_gb`, queue depth)

## Notes

- Use `--disable-metrics` if the API is not running with `/metrics/memory`.
- Use `--no-ping` for long-prefill runs to avoid websocket keepalive timeout bias.
- If output tests stop early, it is model behavior, not necessarily a cap hit.
