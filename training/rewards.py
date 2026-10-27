"""GRPO reward functions. Each component is pure and unit-tested; the TRL-facing
closures are thin adapters built by ``make_reward_funcs``.

Components and weights (see docs/decisions.md for rationale):
  format      x 0.2  - graded: output looks like SQL, parses as one SELECT statement
  execution   x 0.3  - the query runs on the real database without error
  correctness x 1.0  - result multiset matches the gold query's result
  degenerate  x 1.0  - penalty (<= 0) for empty, overlong or repetitive output

The shaping gives partial credit (format, execution) so early training has a
dense signal, while correctness dominates the total so no combination of
cosmetic rewards can beat actually answering the question. The degenerate
penalty removes the classic collapse modes GRPO finds first.
"""

import re
from collections.abc import Callable
from pathlib import Path

from sqlforge.data.prompting import extract_sql
from sqlforge.eval.metrics import has_top_level_order_by, rows_match
from sqlforge.execution import execute_sql, validate_select_only

MAX_COMPLETION_CHARS = 1200
WEIGHTS = {"format": 0.2, "execution": 0.3, "correctness": 1.0, "degenerate": 1.0}


def score_format(completion: str) -> float:
    """[0, 1]: 0.5 for starting like SQL without preamble, 0.5 for parsing cleanly."""
    text = completion.strip()
    score = 0.0
    if re.match(r"^(select|with)\b", text, re.IGNORECASE):
        score += 0.5
    sql = extract_sql(completion)
    if sql and validate_select_only(sql) is None:
        score += 0.5
    return score


def score_execution(
    completion: str, db_path: Path, timeout_s: float = 5.0, row_limit: int = 10_000
) -> float:
    sql = extract_sql(completion)
    if not sql:
        return 0.0
    return 1.0 if execute_sql(db_path, sql, timeout_s=timeout_s, row_limit=row_limit).ok else 0.0


def score_correctness(
    completion: str,
    gold_sql: str,
    db_path: Path,
    timeout_s: float = 5.0,
    row_limit: int = 10_000,
) -> float:
    sql = extract_sql(completion)
    if not sql:
        return 0.0
    gold = execute_sql(db_path, gold_sql, timeout_s=timeout_s, row_limit=row_limit)
    pred = execute_sql(db_path, sql, timeout_s=timeout_s, row_limit=row_limit)
    if not (gold.ok and pred.ok):
        return 0.0
    return float(rows_match(gold.rows, pred.rows, has_top_level_order_by(gold_sql)))


def score_degenerate(completion: str, max_chars: int = MAX_COMPLETION_CHARS) -> float:
    """[-1, 0]: penalties for empty, overlong, or token-repetition collapse."""
    text = completion.strip()
    if not text:
        return -1.0
    penalty = 0.0
    if len(text) > max_chars:
        penalty -= 0.5
    tokens = text.split()
    if len(tokens) >= 8:
        # Any single token making up >50% of the output is repetition collapse.
        top = max(tokens.count(t) for t in set(tokens))
        if top / len(tokens) > 0.5:
            penalty -= 0.5
    return penalty


def make_reward_funcs(
    db_root: Path, timeout_s: float = 5.0, row_limit: int = 10_000
) -> list[Callable]:
    """Build TRL-compatible reward functions, one per component.

    Keeping them separate (instead of one summed reward) makes TRL log each
    component as its own curve - essential for spotting reward hacking.
    Dataset columns ``db_id`` and ``gold`` are forwarded by GRPOTrainer.
    """

    def _db(db_id: str) -> Path:
        return db_root / db_id / f"{db_id}.sqlite"

    def format_reward(completions, **_):
        return [WEIGHTS["format"] * score_format(c) for c in completions]

    def execution_reward(completions, db_id, **_):
        return [
            WEIGHTS["execution"] * score_execution(c, _db(d), timeout_s, row_limit)
            for c, d in zip(completions, db_id, strict=True)
        ]

    def correctness_reward(completions, db_id, gold, **_):
        return [
            WEIGHTS["correctness"] * score_correctness(c, g, _db(d), timeout_s, row_limit)
            for c, d, g in zip(completions, db_id, gold, strict=True)
        ]

    def degenerate_penalty(completions, **_):
        return [WEIGHTS["degenerate"] * score_degenerate(c) for c in completions]

    return [format_reward, execution_reward, correctness_reward, degenerate_penalty]
