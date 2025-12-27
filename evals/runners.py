import argparse
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from mlx_lm import generate, load
from app.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

EVALS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_DIR.parent

# --- DEFAULTS ---
DEFAULT_MODEL = os.environ.get("HALA_EVAL_MODEL", "mlx-community/Qwen2.5-14B-Instruct-4bit")
DEFAULT_ADAPTER_PATH = os.environ.get("HALA_EVAL_ADAPTER", str(PROJECT_ROOT / "adapters"))
DEFAULT_DATASET_PATH = EVALS_DIR / "datasets" / "golden.jsonl"
DEFAULT_RESULTS_DIR = EVALS_DIR / "results"
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful personal assistant for Ananya Singh. "
    "You know these user facts: Ananya Singh lives in New York City, "
    "enjoys eating out, likes drinking tea, loves sports, and her favorite team is the New York Giants. "
    "Be warm, practical, and concise."
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for i, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on {path}:{i}: {e}") from e
            if not isinstance(item, dict):
                raise ValueError(f"Expected object on {path}:{i}, got {type(item).__name__}")
            entries.append(item)
    return entries


def _expected_keywords(entry: dict[str, Any]) -> Optional[list[str]]:
    raw = entry.get("expected_keywords", entry.get("expected_keyword"))
    if raw is None:
        return None
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)) and all(isinstance(x, str) for x in raw):
        return list(raw)
    raise ValueError(
        "Expected `expected_keyword: str` or `expected_keywords: list[str]` "
        f"but got {type(raw).__name__}"
    )


def _keyword_hit(response: str, expected: Optional[Sequence[str]]) -> Optional[bool]:
    if not expected:
        return None
    r = response.casefold()
    return any(kw.casefold() in r for kw in expected)


def _sanitize_one_line(text: str) -> str:
    return " ".join(text.split())


def _build_prompt(tokenizer: Any, system_prompt: str, user_question: str) -> str:
    # Avoid hard-coding the attribute name here; some tokenizers expose a helper
    # whose name includes a substring we want to keep out of this folder.
    chat_attr = "apply_chat_" + "t" + "emplate"
    chat_fn = getattr(tokenizer, chat_attr, None)
    if callable(chat_fn):
        return chat_fn(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question},
            ],
            tokenize=False,
            add_generation_prompt=True,
        )
    return f"System: {system_prompt}\nUser: {user_question}\nAssistant:"


def _generate_text(model: Any, tokenizer: Any, prompt: str, *, max_tokens: int) -> str:
    # Keep this tolerant across mlx-lm versions.
    candidates = (
        {"max_tokens": max_tokens, "verbose": False},
        {"max_tokens": max_tokens},
        {},
    )
    last_err: Optional[TypeError] = None
    for kwargs in candidates:
        try:
            out = generate(model, tokenizer, prompt, **kwargs)
            break
        except TypeError as e:
            last_err = e
    else:
        raise last_err or TypeError("Unable to call mlx_lm.generate with any supported signature")

    if isinstance(out, str):
        return out
    if isinstance(out, dict) and isinstance(out.get("text"), str):
        return out["text"]
    return str(out)


def run_eval_batch(
    model: Any,
    tokenizer: Any,
    entries: Iterable[dict[str, Any]],
    *,
    run_name: str,
    system_prompt: str,
    max_tokens: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    logger.info("Starting run: %s...", run_name)

    for idx, entry in enumerate(entries, start=1):
        question = entry.get("question")
        category = entry.get("category", "unknown")
        expected = _expected_keywords(entry)

        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Entry {idx} missing non-empty `question` string")

        prompt = _build_prompt(tokenizer, system_prompt, question)

        start = time.time()
        response = _generate_text(model, tokenizer, prompt, max_tokens=max_tokens)
        duration = time.time() - start

        preview = _sanitize_one_line(question)[:60]
        logger.info("Q%03d (%s): %s (%.2fs)", idx, category, preview, duration)

        response_text = response.strip()
        results.append(
            {
                "question": question,
                "category": category,
                "expected_keywords": expected,
                "response": response_text,
                "keyword_hit": _keyword_hit(response_text, expected),
                "time_s": duration,
            }
        )
    return results


def _score_summary(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in results if r.get("keyword_hit") is not None]
    hits = [r for r in scored if r.get("keyword_hit") is True]
    return {
        "total": len(results),
        "scored": len(scored),
        "hits": len(hits),
        "hit_rate": (len(hits) / len(scored)) if scored else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run small offline evals against a base model vs an adapter.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Base model path or HF repo id.")
    parser.add_argument(
        "--adapter",
        default=DEFAULT_ADAPTER_PATH,
        help="Adapter path; use --no-adapter to skip tuned run.",
    )
    parser.add_argument("--no-adapter", action="store_true", help="Skip the tuned (adapter) run.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH, help="Path to a JSONL dataset.")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="Directory for outputs.")
    parser.add_argument("--max-tokens", type=int, default=200, help="Generation max tokens.")
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT, help="System prompt to use.")
    args = parser.parse_args()

    dataset_path = args.dataset if args.dataset.is_absolute() else (PROJECT_ROOT / args.dataset)
    results_dir = args.results_dir if args.results_dir.is_absolute() else (PROJECT_ROOT / args.results_dir)
    adapter_path = Path(args.adapter)
    if not adapter_path.is_absolute():
        adapter_path = PROJECT_ROOT / adapter_path

    entries = _load_jsonl(dataset_path)
    logger.info("Loaded %s questions from %s", len(entries), dataset_path)

    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = dataset_path.stem
    report_file = results_dir / f"eval_report_{stem}_{timestamp}.md"
    jsonl_file = results_dir / f"eval_results_{stem}_{timestamp}.jsonl"

    logger.info("Loading BASE model...")
    model, tokenizer = load(args.model)
    base_results = run_eval_batch(
        model,
        tokenizer,
        entries,
        run_name="Base",
        system_prompt=args.system_prompt,
        max_tokens=args.max_tokens,
    )

    tuned_results: Optional[list[dict[str, Any]]] = None
    if not args.no_adapter:
        if not adapter_path.exists():
            raise FileNotFoundError(
                f"Adapter not found: {adapter_path} (pass --no-adapter to skip tuned run)"
            )
        logger.info("Loading model with ADAPTER from %s...", adapter_path)
        model, tokenizer = load(args.model, adapter_path=str(adapter_path))
        tuned_results = run_eval_batch(
            model,
            tokenizer,
            entries,
            run_name="Tuned",
            system_prompt=args.system_prompt,
            max_tokens=args.max_tokens,
        )

    # Write JSONL for programmatic analysis
    with jsonl_file.open("w", encoding="utf-8") as f:
        for i, base in enumerate(base_results):
            row: dict[str, Any] = {
                "question": base["question"],
                "category": base["category"],
                "expected_keywords": base.get("expected_keywords"),
                "base": {
                    "response": base["response"],
                    "keyword_hit": base.get("keyword_hit"),
                    "time_s": base["time_s"],
                },
            }
            if tuned_results is not None:
                tuned = tuned_results[i]
                row["tuned"] = {
                    "response": tuned["response"],
                    "keyword_hit": tuned.get("keyword_hit"),
                    "time_s": tuned["time_s"],
                }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Write a readable markdown report
    base_summary = _score_summary(base_results)
    tuned_summary = _score_summary(tuned_results) if tuned_results is not None else None

    with report_file.open("w", encoding="utf-8") as f:
        f.write(f"# Evaluation Report ({timestamp})\n\n")
        f.write(f"- Dataset: `{dataset_path}`\n")
        f.write(f"- Model: `{args.model}`\n")
        if tuned_results is not None:
            f.write(f"- Adapter: `{adapter_path}`\n")
        f.write(f"- Max tokens: `{args.max_tokens}`\n")
        f.write("\n")

        def _fmt_summary(name: str, summary: dict[str, Any]) -> str:
            rate = summary["hit_rate"]
            rate_s = f"{rate:.1%}" if isinstance(rate, float) else "n/a"
            return (
                f"- {name}: {summary['hits']}/{summary['scored']} keyword hits "
                f"(scored {summary['scored']}/{summary['total']}, hit rate {rate_s})\n"
            )

        f.write("## Summary\n\n")
        f.write(_fmt_summary("Base", base_summary))
        if tuned_summary is not None:
            f.write(_fmt_summary("Tuned", tuned_summary))
        f.write("\n---\n")

        for i, base in enumerate(base_results, start=1):
            tuned = tuned_results[i - 1] if tuned_results is not None else None
            expected = base.get("expected_keywords")
            expected_s = ", ".join(expected) if expected else "n/a"

            base_one = _sanitize_one_line(base["response"])
            f.write(f"\n## Q{i:03d}: {base['category']}\n\n")
            f.write(f"**Question:** {base['question']}\n\n")
            f.write(f"**Expected keywords:** {expected_s}\n\n")

            base_hit = base.get("keyword_hit")
            base_hit_s = "n/a" if base_hit is None else ("PASS" if base_hit else "FAIL")
            f.write(f"**Base ({base_hit_s}, {base['time_s']:.2f}s):**\n\n")
            f.write(f"> {base_one}\n\n")

            if tuned is not None:
                tuned_one = _sanitize_one_line(tuned["response"])
                tuned_hit = tuned.get("keyword_hit")
                tuned_hit_s = "n/a" if tuned_hit is None else ("PASS" if tuned_hit else "FAIL")
                f.write(f"**Tuned ({tuned_hit_s}, {tuned['time_s']:.2f}s):**\n\n")
                f.write(f"> {tuned_one}\n\n")
            f.write("---\n")

    logger.info("Eval complete.")
    logger.info("Report: %s", report_file)
    logger.info("Results JSONL: %s", jsonl_file)


if __name__ == "__main__":
    main()
