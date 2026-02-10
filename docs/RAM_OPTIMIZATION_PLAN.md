# RAM Optimization Plan

This document outlines the strategy for reducing the memory footprint of the HalaAI engine, which currently consumes ~17GB of RAM in its steady state.

## Research Findings

The primary memory consumers are:
1. **Model Weights:** The Qwen3-30B-A3B-4bit model requires ~15-18GB of VRAM/RAM for its weights alone.
2. **KV Cache:** Intermediate activations during inference grow linearly with context length. Unbounded, this can lead to memory exhaustion in long conversations.
3. **Unified Memory Pressure:** On Apple Silicon, the GPU and CPU share RAM. Inefficient management leads to aggressive swapping by the OS.
4. **Python Garbage Collection:** High-frequency object creation (tensors, chunks) can outpace the automatic garbage collector.

## Optimization Strategies & Feasibility Ranking

### 1. Strict KV Cache Management (High Impact / Low Risk)
* **Goal:** Cap the maximum size of the Key-Value cache.
* **Why:** Prevents memory leaks during long-context sessions without significantly impacting quality for standard chats.
* **Implementation:** Pass `max_kv_size` to the MLX inference engine and explicitly clear cache after requests.

### 2. Aggressive Garbage Collection (Medium Impact / Low Risk)
* **Goal:** Force Python to reclaim memory immediately after inference tasks.
* **Why:** Python's generational GC may not trigger often enough for large tensor-heavy workloads.
* **Implementation:** Explicitly call `gc.collect()` in the `ModelEngine` worker loop after job completion.

### 3. Wired Memory Limit (Medium Impact / Low Risk)
* **Goal:** Explicitly manage the "wired" memory used by Metal.
* **Why:** Helps the macOS kernel better allocate Unified Memory and reduces swapping performance hits.
* **Implementation:** Use `mlx.core.metal.set_wired_limit()` during engine initialization (macOS 15+).

### 4. ChromaDB Memory Capping (Medium Impact / Low Risk)
* **Goal:** Limit the RAM consumed by the vector database.
* **Why:** Chroma can cache large segments in memory, competing with the LLM for resources.
* **Implementation:** Configure `chroma_memory_limit_bytes` in the memory cortex settings.

### 5. Dynamic Model Unloading (Low Impact / High Risk)
* **Goal:** Fully unload the model weights during long idle periods.
* **Why:** Reclaims almost all RAM.
* **Trade-off:** Introduces massive latency (10s+) for the next request.
* **Decision:** Postponed for now.

## Actionable Roadmap

We will proceed with implementing **Points 1, 2, 3, and 4** as they provide the best balance of safety, speed, and memory savings.

### Phase 1: Engine Hardening
* Integrate `gc.collect()` in `app/engine.py`.
* Set Metal wired memory limits.
* Implement cache pruning logic.

### Phase 2: Context Optimization
* Add `max_kv_size` limits to generation requests.
* Configure ChromaDB memory limits in `core/memory.py`.

### Phase 3: Monitoring
* Add a memory telemetry endpoint to track usage trends over time.

## Implemented Configuration (Now Available)

You can tune the memory controls through `settings.yaml`:

```yaml
engine_memory:
  max_kv_size: 2048
  max_prompt_tokens: 1024
  prompt_token_reserve: 128
  preserve_prompt_head_tokens: 256
  kv_bits: null
  kv_group_size: 64
  quantized_kv_start: 0
  force_gc_after_request: true
  enable_metal_wired_limit: true
  metal_wired_limit_gb: null
  metal_wired_limit_ratio: 0.67

chroma_memory:
  segment_cache_policy: LRU
  memory_limit_bytes: 536870912
```

Memory telemetry endpoint:
* `GET /metrics/memory`
