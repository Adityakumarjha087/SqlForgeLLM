from collections import Counter

from sqlforge.data.pipeline import Example, dedupe, filter_executes, filter_parses, leak_guard
from sqlforge.data.prompting import build_messages, extract_sql
from sqlforge.data.schema import extract_schema


def ex(db_id="concert_db", q="How many concerts?", sql="SELECT count(*) FROM concert"):
    return Example(db_id=db_id, question=q, query=sql)


class TestSchema:
    def test_full_schema_has_create_statements(self, tiny_db):
        schema = extract_schema(tiny_db)
        assert "CREATE TABLE stadium" in schema
        assert "FOREIGN KEY" in schema

    def test_long_schema_falls_back_to_compact(self, tiny_db):
        schema = extract_schema(tiny_db, max_chars=50)
        assert "CREATE TABLE" not in schema
        assert "stadium(" in schema
        assert "capacity INTEGER" in schema


class TestPrompting:
    def test_messages_shape(self):
        messages = build_messages("CREATE TABLE t (x INT);", "How many rows?")
        assert [m["role"] for m in messages] == ["system", "user"]
        assert "How many rows?" in messages[1]["content"]
        assert "CREATE TABLE t" in messages[1]["content"]

    def test_extract_sql_plain(self):
        assert extract_sql("SELECT * FROM t") == "SELECT * FROM t"

    def test_extract_sql_fenced(self):
        assert extract_sql("```sql\nSELECT 1;\n```") == "SELECT 1"

    def test_extract_sql_with_chatter_and_second_statement(self):
        text = "Sure! Here is the query:\nSELECT a\nFROM t;\nDROP TABLE t;"
        assert extract_sql(text) == "SELECT a FROM t"


class TestFilters:
    def test_dedupe_normalizes_whitespace_and_case(self):
        dropped = Counter()
        kept = dedupe([ex(), ex(q="how  many   concerts?")], dropped)
        assert len(kept) == 1
        assert dropped["dedupe"] == 1

    def test_filter_parses_drops_garbage(self):
        dropped = Counter()
        kept = filter_parses([ex(), ex(sql="SELEC nope")], dropped)
        assert len(kept) == 1
        assert dropped["parses"] == 1

    def test_filter_executes_drops_bad_column(self, tiny_db):
        dropped = Counter()
        kept = filter_executes(
            [ex(), ex(sql="SELECT missing_col FROM concert")],
            db_root=tiny_db.parent.parent,
            dropped=dropped,
            timeout_s=5.0,
            row_limit=100,
        )
        assert len(kept) == 1
        assert dropped["executes"] == 1

    def test_leak_guard_drops_test_dbs_from_train(self):
        dropped = Counter()
        train = [ex(), ex(db_id="other_db")]
        test = [ex(db_id="concert_db", q="different q")]
        kept = leak_guard(train, test, dropped)
        assert [e.db_id for e in kept] == ["other_db"]
        assert dropped["leak_guard"] == 1


class TestExtractSqlEdgeCases:
    def test_chatter_containing_the_word_with(self):
        text = "Sure, I can help with that: SELECT a FROM t"
        assert extract_sql(text) == "SELECT a FROM t"

    def test_cte_after_chatter(self):
        text = "Here you go: WITH c AS (SELECT 1 AS x) SELECT x FROM c"
        assert extract_sql(text) == "WITH c AS (SELECT 1 AS x) SELECT x FROM c"

    def test_unparseable_still_returns_earliest_attempt(self):
        assert extract_sql("SELECT frm nope garbage((").startswith("SELECT")

    def test_no_sql_at_all(self):
        assert extract_sql("I cannot answer that.") == "I cannot answer that."
