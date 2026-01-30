# Model Upgrade Research Notes

Date: 2026-01-28

Status update (2026-01-29):
- Base model switched to `mlx-community/Qwen3-30B-A3B-4bit`.
- Legacy throughput baselines reference the prior 14B model; re-benchmark for Qwen3.

## Scope
These notes summarize the research and reasoning behind three upgrade candidates for HalaAI on a Mac Studio M4 base system:

- Qwen2.5-32B (4-bit)
- Qwen3-30B-A3B (4-bit MoE)
- Mistral Small 3.1 24B (4-bit)

This document is intentionally practical: it blends public model cards/tech reports, Apple hardware specs, and local project benchmarks (HalaAI README + local MLX report).

## System Baseline (Local)
- Hardware: Mac Studio M4 base (14-core CPU, 32-core GPU, 36GB unified memory, 410GB/s memory bandwidth).
- Current base model: Qwen3-30B-A3B-4bit (MLX).
- Legacy throughput: ~29.8 tokens/sec avg with peaks ~38 t/s on Qwen2.5-14B (from HalaAI README).

## Public Sources Used (Summary)
- Apple Mac Studio M4 Max specs (CPU/GPU/memory/bandwidth).
- Qwen2.5 and Qwen3 official model cards and technical reports.
- MLX conversion/model cards for memory estimates (where available).
- Mistral Small 3.1 official model card.
- Qwen2.5 / Qwen3 release blog posts for release dates.

## Important Caveat: Knowledge Cutoff Dates
I looked for explicit “knowledge cutoff” or “training data cutoff” dates in official model cards and reports for all three models. None of the official sources publicly state a cutoff date.

For each model, I’ve provided:
- **Cutoff date:** Not disclosed in official materials.
- **Closest dated public source:** Release month/year of the model card, blog, or technical report (not the same thing as a training cutoff).

If you later find official cutoff disclosures, we should replace the “Not disclosed” entries.

---

# 1) Qwen2.5-32B-Instruct (4-bit)

## Model Overview (from official sources)
- Params: 32.5B total (31.0B non-embedding).
- Context length: 131,072 tokens (via YaRN configuration).
- Training stage: Pretraining + post-training (SFT + RL).

## 4-bit memory estimate
- MLX conversion card reports ~18.4 GB for the MLX 4-bit build (weights only). This leaves enough headroom for OS + KV cache on a 36GB machine.

## Why it fits your system
- At 4-bit, weights are well under the 36GB unified memory ceiling.
- Headroom remains for KV cache and the OS, as long as you avoid ultra-long contexts.

## Inference projection (vs current ~30 t/s)
- Projected: ~12–18 t/s (about 1.7–2.5× slower than current 14B).

## Pros
- Stronger reasoning and instruction-following than 14B.
- Long context support with YaRN.
- Mature, widely supported model family.

## Cons
- Slower throughput than current model.
- Larger KV cache impact at long contexts.
- Existing LoRA adapters for 14B are not compatible.

## Training data cutoff (official)
- **Not disclosed** in official model card or technical report.
- Closest dated public source: Qwen2.5 release blog (September 2024) and Qwen2.5 technical report (Dec 2024 / Jan 2025 revisions).

---

# 2) Qwen3-30B-A3B (4-bit MoE)

## Model Overview (from official sources)
- Params: 30.5B total, 3.3B activated per token.
- Architecture: MoE with 128 experts (8 active).
- Context length: 32,768 native; 131,072 with YaRN.

## 4-bit memory estimate
- 4-bit variants reported by community quantizations are ~16.9–17.1 GB for weights (AWQ/GGUF). MLX-specific 4-bit estimates may differ slightly.

## Why it fits your system
- Similar memory footprint to dense 32B, but with much lower active compute per token.
- Likely to preserve more of your current throughput while increasing reasoning quality.

## Inference projection (vs current ~30 t/s)
- Projected: ~20–35 t/s (about 0.9–1.5× slower, sometimes near parity depending on prompt and mode).

## Pros
- Best speed-to-quality ratio of the three (MoE efficiency).
- Strong agent/tool performance; “thinking” mode support.
- Long context support with YaRN.

## Cons
- MoE routing can yield higher variance in output quality.
- Community quantizations may vary in quality and tooling support.

## Training data cutoff (official)
- **Not disclosed** in official model card or technical report.
- Closest dated public source: Qwen3 release blog (April 2025) and Qwen3 technical report (arXiv 2505.09388, May 2025).

---

# 3) Mistral Small 3.1 24B (4-bit)

## Model Overview (from official sources)
- Params: 24B.
- Context length: up to 128K tokens.
- Model card notes it fits within a 32GB RAM MacBook once quantized.

## 4-bit memory estimate
- 24B at 4-bit generally lands around ~12–14 GB for weights. This leaves large headroom for KV cache and multitasking on a 36GB system.

## Why it fits your system
- Highest headroom and most stability in memory usage.
- Allows higher-precision quants (6-bit/8-bit) if you want more quality.

## Inference projection (vs current ~30 t/s)
- Projected: ~18–25 t/s (about 1.2–1.7× slower).

## Pros
- Strong general model with large headroom.
- 128K context supported.
- Likely the most stable and “boring” deployment option.

## Cons
- Slightly lower reasoning ceiling than the 30–32B options.
- MLX-specific 4-bit conversions may be less standardized than Qwen’s MLX community builds.

## Training data cutoff (official)
- **Not disclosed** in the official model card.
- Closest dated public source: model card release info and third-party quantized variants around April 2025.

---

# Quick Comparison Table (Projected)

| Model | Params | 4-bit Weights (approx) | Projected t/s | Slowdown vs 14B | Cutoff Date (official) |
|---|---:|---:|---:|---:|---|
| Qwen2.5-32B | 32.5B | ~18.4 GB (MLX) | ~12–18 | ~1.7–2.5× | Not disclosed (release Sep 2024) |
| Qwen3-30B-A3B | 30.5B (3.3B active) | ~16.9–17.1 GB (4-bit) | ~20–35 | ~0.9–1.5× | Not disclosed (release Apr 2025) |
| Mistral Small 3.1 24B | 24B | ~12–14 GB (4-bit) | ~18–25 | ~1.2–1.7× | Not disclosed (release Apr 2025) |

Notes:
- t/s figures are projections, not measured benchmarks.
- “4-bit weights” are from MLX for Qwen2.5; other models are based on community quantizations and may differ from MLX builds.
- “Release date” is not a training cutoff.

---

# Sources (Public)
- Apple Mac Studio M4 Max specs: https://www.apple.com/mac-studio/specs/
- Qwen2.5-32B model card: https://huggingface.co/Qwen/Qwen2.5-32B-Instruct
- Qwen2.5 MLX 4-bit conversion: https://huggingface.co/mlx-community/Qwen2.5-32B-Instruct-4bit
- Qwen2.5 technical report: https://arxiv.org/abs/2412.15115
- Qwen2.5 blog (release date): https://qwenlm.github.io/blog/qwen2.5-llm/
- Qwen3-30B-A3B model card: https://huggingface.co/Qwen/Qwen3-30B-A3B
- Qwen3 blog (release date): https://qwenlm.github.io/blog/qwen3/
- Mistral Small 3.1 24B model card: https://huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct-2503

# Sources (Local)
- HalaAI README (throughput baseline): /Users/ananyasingh/hala-ai/README.md
- MLX LLMs for Mac Studio M4 report (memory guidance): /Users/ananyasingh/Downloads/MLX LLMs for Mac Studio M4.pdf
