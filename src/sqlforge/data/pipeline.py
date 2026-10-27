"""Spider processing pipeline: load -> filter -> split -> JSONL.

Filters (each logs how many examples it drops):
1. dedupe        - same (db_id, question, query) after normalization
2. parses        - gold SQL must parse as sqlite via sqlglot
3. executes      - gold SQL must run on its database within the timeout
4. leak_guard    - drop any train example whose database appears in the test set

The official Spider dev set is our held-out test set and is never trained on.
"""

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from tqdm import tqdm

from sqlforge.data.schema import extract_schema
from sqlforge.execution import execute_sql, validate_select_only


@dataclass
class Example:
    db_id: str
    question: str
    query: str
    schema: str = ""
    source: str = ""  # train_spider | train_others | dev


@dataclass
class PipelineReport:
    initial: dict[str, int]
    dropped: dict[str, int]
    final: dict[str, int]
    train_dbs: int
    test_dbs: int


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def load_split(path: Path, source: str) -> list[Example]:
    records = json.loads(path.read_text())
    return [
        Example(
            db_id=r["db_id"],
            question=r["question"].strip(),
            query=r["query"].strip(),
            source=source,
        )
        for r in records
    ]


def dedupe(examples: list[Example], dropped: Counter) -> list[Example]:
    seen: set[tuple[str, str, str]] = set()
    kept = []
    for ex in examples:
        key = (ex.db_id, _norm(ex.question), _norm(ex.query))
        if key in seen:
            dropped["dedupe"] += 1
        else:
            seen.add(key)
            kept.append(ex)
    return kept


def filter_parses(examples: list[Example], dropped: Counter) -> list[Example]:
    kept = []
    for ex in examples:
        if validate_select_only(ex.query) is None:
            kept.append(ex)
        else:
            dropped["parses"] += 1
    return kept


def filter_executes(
    examples: list[Example],
    db_root: Path,
    dropped: Counter,
    timeout_s: float,
    row_limit: int,
) -> list[Example]:
    kept = []
    for ex in tqdm(examples, desc="execute gold", unit="ex"):
        result = execute_sql(
            db_root / ex.db_id / f"{ex.db_id}.sqlite",
            ex.query,
            timeout_s=timeout_s,
            row_limit=row_limit,
        )
        if result.ok:
            kept.append(ex)
        else:
            dropped["executes"] += 1
    return kept


def leak_guard(train: list[Example], test: list[Example], dropped: Counter) -> list[Example]:
    test_dbs = {ex.db_id for ex in test}
    kept = []
    for ex in train:
        if ex.db_id in test_dbs:
            dropped["leak_guard"] += 1
        else:
            kept.append(ex)
    return kept


def attach_schemas(examples: list[Example], db_root: Path, max_chars: int) -> None:
    cache: dict[str, str] = {}
    for ex in examples:
        if ex.db_id not in cache:
            cache[ex.db_id] = extract_schema(
                db_root / ex.db_id / f"{ex.db_id}.sqlite", max_chars=max_chars
            )
        ex.schema = cache[ex.db_id]


def write_jsonl(examples: list[Example], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for ex in examples:
            f.write(json.dumps(asdict(ex), ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[Example]:
    return [Example(**json.loads(line)) for line in path.read_text().splitlines() if line]


def run_pipeline(
    spider_dir: Path,
    out_dir: Path,
    include_train_others: bool = True,
    max_schema_chars: int = 4000,
    exec_timeout_s: float = 10.0,
    exec_row_limit: int = 10_000,
) -> PipelineReport:
    db_root = spider_dir / "database"
    train = load_split(spider_dir / "train_spider.json", "train_spider")
    if include_train_others:
        train += load_split(spider_dir / "train_others.json", "train_others")
    test = load_split(spider_dir / "dev.json", "dev")
    initial = {"train": len(train), "test": len(test)}

    train_dropped: Counter = Counter()
    test_dropped: Counter = Counter()

    train = dedupe(train, train_dropped)
    train = filter_parses(train, train_dropped)
    train = filter_executes(train, db_root, train_dropped, exec_timeout_s, exec_row_limit)
    train = leak_guard(train, test, train_dropped)

    # Test set: never filtered for quality (that would inflate our numbers), but
    # gold queries must at least execute, or the metric itself is undefined.
    test = filter_executes(test, db_root, test_dropped, exec_timeout_s, exec_row_limit)

    attach_schemas(train, db_root, max_schema_chars)
    attach_schemas(test, db_root, max_schema_chars)

    write_jsonl(train, out_dir / "train.jsonl")
    write_jsonl(test, out_dir / "test.jsonl")

    dropped = {f"train/{k}": v for k, v in train_dropped.items()}
    dropped.update({f"test/{k}": v for k, v in test_dropped.items()})
    return PipelineReport(
        initial=initial,
        dropped=dropped,
        final={"train": len(train), "test": len(test)},
        train_dbs=len({ex.db_id for ex in train}),
        test_dbs=len({ex.db_id for ex in test}),
    )
