# Evals

Small, script-based evaluations for comparing a base model vs a fine-tuned adapter.

## Datasets

- `evals/datasets/golden.jsonl`: small “personal assistant” sanity set (committed).
- `evals/datasets/golden_general.jsonl`: generated math/econ/logic set (create via script below).

Generate the general dataset:

```bash
python evals/generate_math_econ.py
```

## Run an eval

Run base vs adapter on the default dataset:

```bash
python evals/runners.py
```

Run against a different dataset:

```bash
python evals/runners.py --dataset evals/datasets/golden_general.jsonl
```

Skip the tuned (adapter) run:

```bash
python evals/runners.py --no-adapter
```

Outputs are written to `evals/results/` as both a markdown report and JSONL results.

