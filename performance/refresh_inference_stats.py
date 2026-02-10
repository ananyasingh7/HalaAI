import argparse
import csv
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = BASE_DIR / "inference_logs.db"
DEFAULT_CSV_OUT = BASE_DIR / "performance" / "inferencelog.csv"
DEFAULT_SUMMARY_OUT = BASE_DIR / "performance" / "INFERENCE_STATS.md"

FIELDS = [
    "id",
    "timestamp",
    "request_id",
    "adapter_name",
    "prompt",
    "system_prompt",
    "response_text",
    "tokens_in",
    "tokens_out",
    "total_time_sec",
    "tokens_per_sec",
    "model_name",
    "temp",
    "gpu_usage_pct",
    "cpu_usage_pct",
    "gpu_temp_c",
    "ram_usage_pct",
    "wattage",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh performance/inferencelog.csv and markdown stats from inference_logs.db."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to inference_logs.db")
    parser.add_argument("--csv-out", default=str(DEFAULT_CSV_OUT), help="Output CSV path")
    parser.add_argument("--summary-out", default=str(DEFAULT_SUMMARY_OUT), help="Output markdown path")
    parser.add_argument("--recent-days", type=int, default=30, help="Recent-window size for summary stats")
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model_name filter (e.g. mlx-community/Qwen3-30B-A3B-4bit)",
    )
    return parser.parse_args()


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _load_rows(conn: sqlite3.Connection, model_filter: str | None) -> list[sqlite3.Row]:
    where_clause = ""
    params: tuple = ()
    if model_filter:
        where_clause = "where model_name = ?"
        params = (model_filter,)

    query = (
        "select id, timestamp, request_id, adapter_name, prompt, system_prompt, response_text, "
        "tokens_in, tokens_out, total_time_sec, tokens_per_sec, model_name, temp, gpu_usage_pct, "
        "cpu_usage_pct, gpu_temp_c, ram_usage_pct, wattage "
        f"from inferencelog {where_clause} order by id"
    )
    cur = conn.execute(query, params)
    return cur.fetchall()


def _write_csv(rows: list[sqlite3.Row], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in FIELDS})


def _to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 0:
        return (ordered[mid - 1] + ordered[mid]) / 2
    return ordered[mid]


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return ordered[index]


def _format_metric_block(rows: list[sqlite3.Row], label: str) -> list[str]:
    tps = [float(row["tokens_per_sec"]) for row in rows if row["tokens_per_sec"] is not None]
    tokens_in = [int(row["tokens_in"]) for row in rows if row["tokens_in"] is not None]
    tokens_out = [int(row["tokens_out"]) for row in rows if row["tokens_out"] is not None]
    total_time = [float(row["total_time_sec"]) for row in rows if row["total_time_sec"] is not None]
    ram_pct = [float(row["ram_usage_pct"]) for row in rows if row["ram_usage_pct"] is not None]
    gpu_temp = [float(row["gpu_temp_c"]) for row in rows if row["gpu_temp_c"] is not None]

    block = [
        f"### {label}",
        f"- Runs: {len(rows)}",
        f"- Tokens/sec avg: {_mean(tps):.2f}",
        f"- Tokens/sec median: {_median(tps):.2f}",
        f"- Tokens/sec p95: {_p95(tps):.2f}",
        f"- Tokens in avg: {_mean([float(v) for v in tokens_in]):.1f}",
        f"- Tokens out avg: {_mean([float(v) for v in tokens_out]):.1f}",
        f"- Total time avg (s): {_mean(total_time):.2f}",
        f"- RAM usage avg (%): {_mean(ram_pct):.2f}",
        f"- GPU temp avg (C): {_mean(gpu_temp):.2f}",
    ]
    return block


def _write_summary(rows: list[sqlite3.Row], out_path: Path, recent_days: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=timezone.utc)

    timestamps = [_to_dt(row["timestamp"]) for row in rows]
    valid_ts = [item for item in timestamps if item is not None]
    min_ts = min(valid_ts).isoformat() if valid_ts else "n/a"
    max_ts = max(valid_ts).isoformat() if valid_ts else "n/a"

    per_model: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        model_name = row["model_name"] or "unknown"
        per_model[model_name].append(row)

    recent_cutoff = now - timedelta(days=recent_days)
    recent_rows = [
        row for row in rows if (_to_dt(row["timestamp"]) or datetime.min.replace(tzinfo=timezone.utc)) >= recent_cutoff
    ]

    lines: list[str] = []
    lines.append("# Inference Stats")
    lines.append("")
    lines.append(f"- Generated at (UTC): {now.isoformat()}")
    lines.append(f"- Row range (UTC): {min_ts} -> {max_ts}")
    lines.append(f"- Total rows: {len(rows)}")
    lines.append("")
    lines.extend(_format_metric_block(rows, "Overall"))
    lines.append("")
    lines.extend(_format_metric_block(recent_rows, f"Recent ({recent_days} days)"))
    lines.append("")
    lines.append("## Per Model")
    lines.append("")
    for model_name in sorted(per_model.keys()):
        model_rows = per_model[model_name]
        lines.extend(_format_metric_block(model_rows, model_name))
        lines.append("")

    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    db_path = Path(args.db).expanduser().resolve()
    csv_out = Path(args.csv_out).expanduser().resolve()
    summary_out = Path(args.summary_out).expanduser().resolve()

    if not db_path.exists():
        raise SystemExit(f"Database does not exist: {db_path}")

    conn = _connect(db_path)
    try:
        rows = _load_rows(conn, args.model)
    finally:
        conn.close()

    if not rows:
        raise SystemExit("No inference rows found for the selected filter.")

    _write_csv(rows, csv_out)
    _write_summary(rows, summary_out, recent_days=args.recent_days)

    print(f"rows={len(rows)}")
    print(f"csv={csv_out}")
    print(f"summary={summary_out}")


if __name__ == "__main__":
    main()
