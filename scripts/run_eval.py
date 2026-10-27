"""Evaluate a model (HF id, optionally + LoRA adapter) on the processed test set.

Examples:
  # 20-example CPU/MPS smoke test
  uv run python scripts/run_eval.py --name smoke --limit 20 --batch-size 4

  # full baseline on a GPU
  uv run python scripts/run_eval.py --name base-full

  # SFT adapter
  uv run python scripts/run_eval.py --name sft --adapter outputs/sft/adapter

Writes outputs/eval/<name>.json with config, metrics and per-example predictions,
and optionally appends a summary to docs/results.md (--log-results).
"""

import argparse
import datetime
import json
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default=DEFAULT_MODEL, help="HF model id or local path")
    p.add_argument("--adapter", default=None, help="optional PEFT adapter path")
    p.add_argument("--data", default=str(REPO_ROOT / "data/processed/test.jsonl"))
    p.add_argument("--db-root", default=str(REPO_ROOT / "data/raw/spider_data/database"))
    p.add_argument("--name", required=True, help="run name; output file stem")
    p.add_argument("--limit", type=int, default=None, help="evaluate only the first N examples")
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--max-new-tokens", type=int, default=256)
    p.add_argument("--timeout-s", type=float, default=10.0)
    p.add_argument("--device", default=None, help="cuda | mps | cpu (default: auto)")
    p.add_argument("--log-results", action="store_true", help="append summary to docs/results.md")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    from sqlforge.data.pipeline import read_jsonl
    from sqlforge.eval.generate import generate_sql, load_model
    from sqlforge.eval.metrics import score_prediction
    from sqlforge.seeding import set_seed

    set_seed(42)
    examples = read_jsonl(Path(args.data))
    if args.limit:
        examples = examples[: args.limit]
    print(f"Evaluating {args.model} (+{args.adapter or 'no adapter'}) on {len(examples)} examples")

    lm = load_model(args.model, adapter_path=args.adapter, device=args.device)
    print(f"Device: {lm.device}")
    t0 = time.monotonic()
    predictions = generate_sql(
        lm, examples, batch_size=args.batch_size, max_new_tokens=args.max_new_tokens
    )
    gen_seconds = time.monotonic() - t0

    db_root = Path(args.db_root)
    records, n_exec, n_exact, n_pred_err = [], 0, 0, 0
    for ex, pred in zip(examples, predictions, strict=True):
        score = score_prediction(
            db_root / ex.db_id / f"{ex.db_id}.sqlite", ex.query, pred, timeout_s=args.timeout_s
        )
        n_exec += score.execution_match
        n_exact += score.exact_match
        n_pred_err += score.pred_error is not None
        records.append(
            {
                "db_id": ex.db_id,
                "question": ex.question,
                "gold": ex.query,
                "pred": pred,
                "execution_match": score.execution_match,
                "exact_match": score.exact_match,
                "pred_error": score.pred_error,
            }
        )

    n = len(examples)
    metrics = {
        "execution_accuracy": n_exec / n,
        "exact_match": n_exact / n,
        "pred_error_rate": n_pred_err / n,
        "n_examples": n,
        "generation_seconds": round(gen_seconds, 1),
    }
    out_path = REPO_ROOT / "outputs" / "eval" / f"{args.name}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"config": vars(args), "metrics": metrics, "predictions": records}, indent=2)
    )
    print(json.dumps(metrics, indent=2))
    print(f"Saved {out_path}")

    if args.log_results:
        commit = (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            ).stdout.strip()
            or "unknown"
        )
        line = (
            f"\n## {datetime.date.today()} — Eval `{args.name}` (commit {commit})\n\n"
            f"- Model: `{args.model}`"
            + (f" + adapter `{args.adapter}`" if args.adapter else "")
            + f"\n- Examples: {n} — **execution accuracy {metrics['execution_accuracy']:.1%}**, "
            f"exact match {metrics['exact_match']:.1%}, "
            f"pred errors {metrics['pred_error_rate']:.1%}\n"
        )
        results = REPO_ROOT / "docs" / "results.md"
        results.write_text(results.read_text() + line)


if __name__ == "__main__":
    main()
