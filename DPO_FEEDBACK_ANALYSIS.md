# DPO Feedback Loop Analysis (HalaAI)

Date: 2026-01-19

## Scope
This document summarizes the analysis of adding thumbs-up/down feedback, preference-pair storage, and alignment tuning for HalaAI. It covers what is good, what is risky, options, constraints, and a proposed path that works on a Mac Studio M4.

## Summary (TL;DR)
- The vision is sound for collecting preference data, but raw thumbs-up alone does not produce DPO pairs.
- DPO requires pairwise (chosen vs rejected) data and a DPO training loop, which is not available in the current MLX fine-tune script.
- A lightweight M4-only path is to do SFT on corrected answers (and optionally thumbs-up) with careful curation, then evaluate before swapping adapters.
- True DPO is feasible later if you add a DPO-capable trainer (likely PyTorch/TRL on a GPU box) or implement DPO in MLX.

## Good
- Thumbs-down + corrected answer maps cleanly to a preference pair:
  - Rejected = model response
  - Chosen = user correction
- This is compatible with standard DPO datasets (prompt, chosen, rejected).
- The loop can be fully automated with nightly batching and adapter swaps.

## Bad / Risks
- Thumbs-up alone does not create a DPO pair (no rejected response).
- Missing context (system prompt, history, tools, memories) makes pairs noisy and can harm training.
- User corrections can drift style/tone and weaken the intended assistant persona.
- Small daily batches can cause overfitting or regressions.
- Current MLX LoRA fine-tune path is SFT only, not DPO.

## Constraints
- Hardware: Mac Studio M4 only (no external GPU box).
- Current training path: `app/fine_tune.py` uses MLX LoRA SFT.
- DPO training is not implemented in MLX (would require custom work).

## Options
1) **M4-only SFT (recommended now)**
   - Use corrected answers (thumbs-down) as supervised training examples.
   - Optionally include thumbs-up as additional SFT data with lower weight.
   - Train a dedicated LoRA adapter periodically and evaluate.

2) **True DPO on GPU (later)**
   - Export preference pairs to a DPO trainer (e.g., TRL) on a GPU box.
   - Bring back LoRA adapter weights to the Mac for inference.

3) **Implement DPO in MLX (longer-term)**
   - Build pairwise preference loss directly in MLX.
   - Highest engineering cost; would keep everything local.

## Proposed Solution (M4-only, lightweight)
- Collect feedback in HalaAI via thumbs-up/down.
- Thumbs-down requires a corrected response.
- Store full prompt context with each feedback event:
  - system prompt, history window, tool/search context, adapter name, params.
- Build a curated SFT dataset from corrected answers.
- Train LoRA adapter nightly only after hitting a minimum data threshold (e.g., 200+ examples).
- Run your existing evals before swapping adapters; keep rollback adapters.

## Data Notes
- For high quality training, use the exact prompt context that generated the response.
- Include a short taxonomy for why it was wrong (fact, tone, safety, incomplete) to filter later.

## Next Steps
- Define the feedback schema in HalaAI DB.
- Add UI controls for thumbs-up/down and correction capture.
- Build an export script for SFT dataset.
- Schedule SFT training on the Mac and adapter evaluation.
