"""Milestone 5: categorize test examples by SQL features and difficulty.

Features come from parsing the *gold* query with sqlglot (the prediction's
features would shift with the model under study). Difficulty is an approximation
of Spider's official hardness - a component count over the same ingredients
(joins, aggregation, nesting, set ops, ...) - documented as such; we report it
alongside, not instead of, the feature categories.
"""

import sqlglot
from sqlglot import exp

FEATURES = ["join", "group_by", "nested", "order_limit", "set_op", "aggregation"]


def categorize(sql: str) -> set[str]:
    """Which SQL features does this (gold) query use?"""
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return set()
    features: set[str] = set()
    if list(tree.find_all(exp.Join)):
        features.add("join")
    if list(tree.find_all(exp.Group)):
        features.add("group_by")
    if len(list(tree.find_all(exp.Select))) > 1:
        features.add("nested")
    if list(tree.find_all(exp.Order)) or list(tree.find_all(exp.Limit)):
        features.add("order_limit")
    if list(tree.find_all(exp.Union, exp.Except, exp.Intersect)):
        features.add("set_op")
    if list(tree.find_all(exp.AggFunc)):
        features.add("aggregation")
    return features


def difficulty(sql: str) -> str:
    """Approximate Spider hardness: easy / medium / hard / extra."""
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return "extra"
    score = (
        len(list(tree.find_all(exp.Join)))
        + len(list(tree.find_all(exp.Group)))
        + len(list(tree.find_all(exp.Order)))
        + len(list(tree.find_all(exp.AggFunc)))
        + 2 * (len(list(tree.find_all(exp.Select))) - 1)
        + 2 * len(list(tree.find_all(exp.Union, exp.Except, exp.Intersect)))
        + len(list(tree.find_all(exp.Where)))
    )
    if score <= 1:
        return "easy"
    if score <= 3:
        return "medium"
    if score <= 6:
        return "hard"
    return "extra"


def accuracy_by_category(predictions: list[dict]) -> dict[str, dict]:
    """Per-feature and per-difficulty execution accuracy for one eval run.

    ``predictions`` are records from an eval JSON (need: gold, execution_match).
    Returns {category: {"n": int, "accuracy": float}}; an example counts toward
    every feature its gold query uses.
    """
    buckets: dict[str, list[bool]] = {f: [] for f in FEATURES}
    buckets.update({f"difficulty/{d}": [] for d in ["easy", "medium", "hard", "extra"]})
    buckets["overall"] = []
    for record in predictions:
        match = bool(record["execution_match"])
        buckets["overall"].append(match)
        for feature in categorize(record["gold"]):
            buckets[feature].append(match)
        buckets[f"difficulty/{difficulty(record['gold'])}"].append(match)
    return {
        name: {"n": len(marks), "accuracy": sum(marks) / len(marks) if marks else 0.0}
        for name, marks in buckets.items()
    }
