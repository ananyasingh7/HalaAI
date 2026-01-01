# Stress Test Notes (HalaAI)

This log summarizes the stress tests run so far, based on the terminal output in this chat. It captures what worked, what failed, and why.

## Environment
- Script: `performance/stress_test.py`
- Server: WebSocket streaming path (`/ws/chat/v2`)
- Logs source: `inference_logs.db` (table `inferencelog`)

## Context (Input) Sweep

### Run 1
Command:
```
python3 performance/stress_test.py --mode context --context-max 8192
```
Results:
- 128 words -> tokens_in=157
- 256 words -> tokens_in=285
- 512 words -> tokens_in=541
- 1024 words -> tokens_in=1053
- 2048 words -> tokens_in=2077
- 4096 words -> tokens_in=4125
- 8192 words -> tokens_in=8221
Observation:
- No hard failure up to ~8.2k input tokens.
- Latency increased roughly linearly as prompt size grew.

### Run 2 (Keepalive timeout)
Command:
```
python3 performance/stress_test.py --mode context --context-max 16384
```
Results:
- Succeeded up to 8192 words (tokens_in=8221)
- Failed at 16384 words with:
  `sent 1011 (internal error) keepalive ping timeout; no close frame received`
Observation:
- Failure was due to WebSocket keepalive timeout, not necessarily a hard context limit.

### Run 3 (No ping)
Command:
```
python3 performance/stress_test.py --mode context --context-max 24576 --no-ping
```
Results:
- 16384 words -> tokens_in=16413 (success)
Observation:
- Disabling keepalives avoided the timeout.
- Context limit still not reached at ~16.4k input tokens.

## Output (Generation) Sweep

### Run 1 (Short prompt, early stop)
Command:
```
python performance/stress_test.py --mode output --output-max 24576 --no-ping
```
Results:
- tokens_out stayed ~21-22 across max_tokens 512..16384
Observation:
- Model stopped early; max_tokens is a cap, not a target.

### Run 2 (System prompt: numbers)
Command:
```
python performance/stress_test.py --mode output --output-max 24576 --no-ping \
  --system-prompt "Output a list of numbers from 1 to 20000, one per line. Do not stop early."
```
Results:
- tokens_out ranged ~114-195
Observation:
- Slightly longer outputs, but still early stop.

### Run 3 (Preset: lines)
Command:
```
python performance/stress_test.py --mode output --output-max 24576 --no-ping --prompt-preset lines
```
Results:
- tokens_out ranged ~67-154
Observation:
- Still early stop; model does not honor “keep going” reliably.

### Run 4 (Custom prompt: A on each line)
Command:
```
python performance/stress_test.py --mode output --output-max 24576 --no-ping \
  --prompt "Print the character 'A' on a new line 20000 times. No other text. Start now."
```
Results:
- tokens_out ranged ~93-146
Observation:
- Still early stop; no max-output cap was reached.

## Good
- Context sweep shows stable scaling and no hard failure up to ~16.4k input tokens.
- Throughput (tokens/sec) remains consistent for short outputs.
- `--no-ping` avoids WebSocket keepalive timeouts for long prompts.

## Bad / Limitations Observed
- Output sweeps do not reach max_tokens because the model stops early.
- Without a `min_tokens` constraint or different decoding settings, “max output” tests are not representative.
- Keepalive timeouts can occur on long-prefill runs unless pings are disabled or timeouts are increased.

## Next Steps (Optional)
- Add `min_tokens` support in the server to force longer generations.
- Add a “combined context+output” test to find true total window.
- Add a binary-search mode to quickly find the max context length.
