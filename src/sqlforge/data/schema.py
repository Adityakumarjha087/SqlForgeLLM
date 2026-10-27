"""Turn a SQLite database into schema text for the prompt.

Default form: the original CREATE TABLE statements (whitespace-collapsed), which
preserve primary/foreign keys the model needs for joins. If the combined schema
exceeds ``max_chars``, fall back to a compact ``table(col type, ...)`` listing -
lossy (drops constraints) but keeps the prompt inside the context budget.
"""

import re
import sqlite3
from pathlib import Path


def _connect_ro(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    return conn


def _collapse_ws(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def extract_schema(db_path: str | Path, max_chars: int = 4000) -> str:
    """Return schema text for ``db_path``, at most ~max_chars long."""
    conn = _connect_ro(db_path)
    try:
        creates = [
            _collapse_ws(row[0])
            for row in conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY name"
            )
        ]
        full = "\n".join(f"{c};" for c in creates)
        if len(full) <= max_chars:
            return full
        return _compact_schema(conn)
    finally:
        conn.close()


def _compact_schema(conn: sqlite3.Connection) -> str:
    lines = []
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    for table in tables:
        cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        col_text = ", ".join(f"{c[1]} {c[2]}".strip() for c in cols)
        lines.append(f"{table}({col_text})")
    return "\n".join(lines)
