"""Execution accuracy (primary) and exact match (secondary).

Execution accuracy: run gold and predicted SQL on the example's database and
compare result multisets. Order-insensitive unless the gold query has a
top-level ORDER BY. Duplicates matter (multiset, not set); floats are rounded
to absorb representation noise; NULLs compare as themselves.

Known limitation (accepted, standard for Spider): a wrong query can return the
right rows on a particular database state - e.g. a missing ORDER BY passes if
the data happens to be sorted. Exact match is reported alongside as a stricter,
but syntax-brittle, signal.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import sqlglot

from sqlforge.execution import execute_sql


def _normalize_value(value):
    if isinstance(value, float):
        return round(value, 5)
    return value


def _normalize_rows(rows: list[tuple]) -> list[tuple]:
    return [tuple(_normalize_value(v) for v in row) for row in rows]


def has_top_level_order_by(sql: str) -> bool:
    try:
        parsed = sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return False
    return parsed.args.get("order") is not None


def rows_match(gold_rows: list[tuple], pred_rows: list[tuple], order_sensitive: bool) -> bool:
    gold, pred = _normalize_rows(gold_rows), _normalize_rows(pred_rows)
    if order_sensitive:
        return gold == pred
    return Counter(gold) == Counter(pred)


def canonical_sql(sql: str) -> str:
    """Canonical form for exact match: parsed and re-rendered, lowercased."""
    try:
        rendered = sqlglot.transpile(sql, read="sqlite", write="sqlite", pretty=False)[0]
    except (sqlglot.errors.ParseError, IndexError):
        rendered = sql
    return " ".join(rendered.lower().split())


def exact_match(pred_sql: str, gold_sql: str) -> bool:
    return canonical_sql(pred_sql) == canonical_sql(gold_sql)


@dataclass
class ExampleScore:
    execution_match: bool
    exact_match: bool
    pred_error: str | None = None


def score_prediction(
    db_path: str | Path,
    gold_sql: str,
    pred_sql: str,
    timeout_s: float = 10.0,
    row_limit: int = 10_000,
) -> ExampleScore:
    em = exact_match(pred_sql, gold_sql)
    gold_result = execute_sql(db_path, gold_sql, timeout_s=timeout_s, row_limit=row_limit)
    if not gold_result.ok:
        # Pipeline guarantees executable gold; treat violations as scoring errors.
        return ExampleScore(False, em, pred_error=f"gold failed: {gold_result.error}")
    pred_result = execute_sql(db_path, pred_sql, timeout_s=timeout_s, row_limit=row_limit)
    if not pred_result.ok:
        return ExampleScore(False, em, pred_error=pred_result.error)
    order_sensitive = has_top_level_order_by(gold_sql)
    return ExampleScore(rows_match(gold_result.rows, pred_result.rows, order_sensitive), em)
