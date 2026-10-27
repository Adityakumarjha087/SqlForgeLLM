"""Safe SQLite execution, shared by the data pipeline, eval harness, GRPO rewards
and the serving layer.

Safety properties:
- read-only connection (``mode=ro`` URI), so even a hostile query cannot write
- only a single SELECT-shaped statement is accepted (validated by parsing with
  sqlglot, not by string matching)
- a deadline enforced via sqlite's progress handler interrupts runaway queries
- results are capped at a row limit and flagged as truncated
"""

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import sqlglot
from sqlglot import exp

DEFAULT_TIMEOUT_S = 10.0
DEFAULT_ROW_LIMIT = 10_000
# How many sqlite VM instructions between progress-handler calls; small enough
# to make the deadline accurate, large enough not to slow queries measurably.
PROGRESS_HANDLER_N = 10_000


@dataclass
class ExecutionResult:
    ok: bool
    rows: list[tuple] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    error: str | None = None
    truncated: bool = False
    elapsed_s: float = 0.0


def validate_select_only(sql: str) -> str | None:
    """Return an error message unless ``sql`` is exactly one SELECT-shaped statement."""
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.ParseError as err:
        return f"parse error: {err.errors[0]['description'] if err.errors else err}"
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return f"expected exactly 1 statement, got {len(statements)}"
    if not isinstance(statements[0], exp.Query):
        return f"only SELECT queries are allowed, got {statements[0].key.upper()}"
    return None


def execute_sql(
    db_path: str | Path,
    sql: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> ExecutionResult:
    """Execute one SELECT statement against a SQLite file, read-only and bounded."""
    validation_error = validate_select_only(sql)
    if validation_error is not None:
        return ExecutionResult(ok=False, error=validation_error)

    db_path = Path(db_path)
    if not db_path.exists():
        return ExecutionResult(ok=False, error=f"database not found: {db_path}")

    start = time.monotonic()
    deadline = start + timeout_s
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout_s)
    except sqlite3.Error as err:
        return ExecutionResult(ok=False, error=f"connect error: {err}")

    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, PROGRESS_HANDLER_N)
    # Spider DBs predate strict text encoding; tolerate non-UTF8 bytes.
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(row_limit + 1)
        truncated = len(rows) > row_limit
        columns = [d[0] for d in cursor.description] if cursor.description else []
        return ExecutionResult(
            ok=True,
            rows=[tuple(r) for r in rows[:row_limit]],
            columns=columns,
            truncated=truncated,
            elapsed_s=time.monotonic() - start,
        )
    except sqlite3.OperationalError as err:
        msg = str(err)
        if "interrupted" in msg:
            msg = f"timeout after {timeout_s}s"
        return ExecutionResult(ok=False, error=msg, elapsed_s=time.monotonic() - start)
    except sqlite3.Error as err:
        return ExecutionResult(ok=False, error=str(err), elapsed_s=time.monotonic() - start)
    finally:
        conn.close()
