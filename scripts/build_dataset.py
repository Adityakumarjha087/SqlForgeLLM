"""Run the Milestone 1 data pipeline and append a data report to docs/results.md.

Usage: uv run python scripts/build_dataset.py
"""

import datetime
import subprocess
from pathlib import Path

from pydantic import BaseModel

from sqlforge.config import load_config
from sqlforge.data.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]


class DataConfig(BaseModel):
    hf_repo: str
    zip_name: str
    raw_dir: str
    processed_dir: str
    include_train_others: bool
    max_schema_chars: int
    exec_timeout_s: float
    exec_row_limit: int
    seed: int


def git_hash() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    cfg = load_config(REPO_ROOT / "configs" / "data.yaml", DataConfig)
    report = run_pipeline(
        spider_dir=REPO_ROOT / cfg.raw_dir / "spider_data",
        out_dir=REPO_ROOT / cfg.processed_dir,
        include_train_others=cfg.include_train_others,
        max_schema_chars=cfg.max_schema_chars,
        exec_timeout_s=cfg.exec_timeout_s,
        exec_row_limit=cfg.exec_row_limit,
    )

    lines = [
        "",
        f"## {datetime.date.today()} — Data pipeline (commit {git_hash()})",
        "",
        f"- Input: {report.initial['train']} train / {report.initial['test']} test examples",
        "- Dropped: "
        + (", ".join(f"{k}: {v}" for k, v in sorted(report.dropped.items())) or "none"),
        f"- Output: **{report.final['train']} train / {report.final['test']} test**",
        f"- Databases: {report.train_dbs} train, {report.test_dbs} test "
        "(overlap enforced to be zero)",
        "",
    ]
    results = REPO_ROOT / "docs" / "results.md"
    results.write_text(results.read_text() + "\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
