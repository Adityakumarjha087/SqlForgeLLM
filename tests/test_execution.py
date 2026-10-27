from sqlforge.execution import execute_sql, validate_select_only


def test_select_returns_rows(tiny_db):
    result = execute_sql(tiny_db, "SELECT name FROM stadium ORDER BY stadium_id")
    assert result.ok
    assert result.rows == [("Big Arena",), ("Small Field",)]
    assert result.columns == ["name"]


def test_rejects_non_select(tiny_db):
    for sql in [
        "INSERT INTO stadium VALUES (3, 'x', 1)",
        "DROP TABLE stadium",
        "UPDATE stadium SET capacity = 0",
        "DELETE FROM concert",
    ]:
        result = execute_sql(tiny_db, sql)
        assert not result.ok, sql
        assert "SELECT" in result.error


def test_rejects_multiple_statements(tiny_db):
    result = execute_sql(tiny_db, "SELECT 1; SELECT 2")
    assert not result.ok


def test_rejects_unparseable(tiny_db):
    result = execute_sql(tiny_db, "SELEC blah frm")
    assert not result.ok


def test_allows_cte_and_union(tiny_db):
    assert validate_select_only("WITH t AS (SELECT 1 AS x) SELECT x FROM t") is None
    assert validate_select_only("SELECT 1 UNION SELECT 2") is None


def test_write_blocked_by_readonly_connection(tiny_db):
    # Belt and braces: even if validation were bypassed, mode=ro blocks writes.
    import sqlite3

    conn = sqlite3.connect(f"file:{tiny_db}?mode=ro", uri=True)
    try:
        conn.execute("INSERT INTO stadium VALUES (9, 'x', 1)")
        raised = False
    except sqlite3.OperationalError:
        raised = True
    finally:
        conn.close()
    assert raised


def test_timeout_interrupts_runaway_query(tiny_db):
    runaway = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c"
    result = execute_sql(tiny_db, runaway, timeout_s=0.3)
    assert not result.ok
    assert "timeout" in result.error
    assert result.elapsed_s < 5


def test_row_limit_truncates(tiny_db):
    result = execute_sql(tiny_db, "SELECT * FROM concert", row_limit=2)
    assert result.ok
    assert len(result.rows) == 2
    assert result.truncated


def test_missing_database():
    result = execute_sql("/nonexistent/x.sqlite", "SELECT 1")
    assert not result.ok
    assert "not found" in result.error
