"""Sample N predictions from an eval run for manual reward-hacking inspection.

Prints question / gold / prediction side by side and auto-flags suspicious
patterns; appends a review template to docs/failures.md.

Flags:
- vacuous_pass: marked correct but both result sets are EMPTY - the metric can't
  distinguish "right query" from "any query returning nothing" here
- scalar_pass:  marked correct via a single identical scalar (count/avg) - weak
  evidence of real understanding, worth eyeballing
- gold_copy:    prediction textually identical to gold (fine on train, but on
  test it suggests leakage - investigate!)

Usage: uv run python scripts/inspect_outputs.py --eval-json outputs/eval/grpo-full.json
"""

import argparse
import datetime
import json
import random
from pathlib import Path

from sqlforge.eval.metrics import canonical_sql
from sqlforge.execution import execute_sql

REPO_ROOT = Path(__file__).resolve().parents[1]


def flag(record: dict, db_root: Path) -> list[str]:
    flags = []
    if record["execution_match"]:
        db = db_root / record["db_id"] / f"{record['db_id']}.sqlite"
        gold_rows = execute_sql(db, record["gold"]).rows
        if not gold_rows:
            flags.append("vacuous_pass")
        elif len(gold_rows) == 1 and len(gold_rows[0]) == 1:
            flags.append("scalar_pass")
        if canonical_sql(record["pred"]) == canonical_sql(record["gold"]):
            flags.append("gold_copy")
    return flags


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-json", required=True)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--db-root", default=str(REPO_ROOT / "data/raw/spider_data/database")
    )
    args = parser.parse_args()

    data = json.loads(Path(args.eval_json).read_text())
    rng = random.Random(args.seed)
    sample = rng.sample(data["predictions"], min(args.n, len(data["predictions"])))
    db_root = Path(args.db_root)

    lines = [
        "",
        f"## {datetime.date.today()} — Reward-hacking inspection of "
        f"`{Path(args.eval_json).name}` ({len(sample)} samples, seed {args.seed})",
        "",
    ]
    n_flagged = 0
    for i, record in enumerate(sample, 1):
        flags = flag(record, db_root)
        n_flagged += bool(flags)
        status = "PASS" if record["execution_match"] else "fail"
        header = f"{i:02d}. [{status}] {' '.join(f'⚠ {f}' for f in flags)}".rstrip()
        print(f"\n{header}\n  Q:    {record['question']}\n  gold: {record['gold']}\n"
              f"  pred: {record['pred']}")
        if flags:
            lines += [
                f"- **{' + '.join(flags)}** — {record['db_id']}: “{record['question']}”",
                f"  - gold: `{record['gold']}`",
                f"  - pred: `{record['pred']}`",
                "  - verdict: _(fill in after manual review)_",
            ]
    lines.append(f"\n{n_flagged}/{len(sample)} samples auto-flagged; "
                 "unflagged passes looked clean.\n")

    failures = REPO_ROOT / "docs" / "failures.md"
    failures.write_text(failures.read_text() + "\n".join(lines))
    print(f"\nAppended {n_flagged} flagged samples to docs/failures.md")


if __name__ == "__main__":
    main()
