"""Latency benchmark against a running SQLForge API.

Sends real test-set questions sequentially (server-side batching is the
backend's job), reports p50/p95 latency and tokens/sec, appends to results.

Usage: uv run python scripts/benchmark_latency.py --url http://localhost:8000 --n 50
"""

import argparse
import datetime
import statistics
from pathlib import Path

import httpx

from sqlforge.data.pipeline import read_jsonl

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--endpoint", default="/generate-sql", choices=["/generate-sql", "/query"])
    parser.add_argument("--data", default=str(REPO_ROOT / "data/processed/test.jsonl"))
    parser.add_argument("--log-results", action="store_true")
    args = parser.parse_args()

    examples = read_jsonl(Path(args.data))[: args.n]
    backend = httpx.get(f"{args.url}/health", timeout=10).json().get("backend", "?")

    latencies, tps_values, failures = [], [], 0
    with httpx.Client(timeout=300) as client:
        # Warm-up request: first call pays model load, excluded from stats.
        client.post(
            f"{args.url}{args.endpoint}",
            json={"question": examples[0].question, "db_id": examples[0].db_id},
        )
        for ex in examples:
            response = client.post(
                f"{args.url}{args.endpoint}",
                json={"question": ex.question, "db_id": ex.db_id},
            )
            if response.status_code != 200:
                failures += 1
                continue
            body = response.json()
            latencies.append(body["latency_ms"])
            if body.get("tokens_per_second"):
                tps_values.append(body["tokens_per_second"])

    if not latencies:
        raise SystemExit(f"all {len(examples)} requests failed")
    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    tps = statistics.median(tps_values) if tps_values else None
    summary = (
        f"backend={backend} endpoint={args.endpoint} n={len(latencies)} "
        f"p50={p50:.0f}ms p95={p95:.0f}ms "
        + (f"tokens/sec(median)={tps:.1f} " if tps else "")
        + (f"failures={failures}" if failures else "")
    ).strip()
    print(summary)

    if args.log_results:
        results = REPO_ROOT / "docs" / "results.md"
        results.write_text(
            results.read_text()
            + f"\n## {datetime.date.today()} — Latency benchmark\n\n- {summary}\n"
        )


if __name__ == "__main__":
    main()
