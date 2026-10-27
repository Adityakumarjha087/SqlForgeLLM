from pathlib import Path

from training.rewards import (
    make_reward_funcs,
    score_correctness,
    score_degenerate,
    score_execution,
    score_format,
)

GOLD = "SELECT count(*) FROM concert"


class TestFormat:
    def test_clean_sql_full_score(self):
        assert score_format("SELECT a FROM t") == 1.0

    def test_fenced_sql_parses_but_has_preamble(self):
        assert score_format("```sql\nSELECT a FROM t\n```") == 0.5

    def test_chatter_then_valid_sql(self):
        assert score_format("Sure, here you go: SELECT a FROM t") == 0.5

    def test_garbage(self):
        assert score_format("I cannot answer that") == 0.0

    def test_non_select_scores_zero_parse_credit(self):
        assert score_format("DROP TABLE t") == 0.0


class TestExecution:
    def test_runs(self, tiny_db):
        assert score_execution("SELECT count(*) FROM concert", tiny_db) == 1.0

    def test_bad_column(self, tiny_db):
        assert score_execution("SELECT nope FROM concert", tiny_db) == 0.0


class TestCorrectness:
    def test_equivalent_query_rewarded(self, tiny_db):
        pred = "SELECT COUNT(concert_id) FROM concert"
        assert score_correctness(pred, GOLD, tiny_db) == 1.0

    def test_wrong_table_not_rewarded(self, tiny_db):
        pred = "SELECT count(*) FROM stadium"
        assert score_correctness(pred, GOLD, tiny_db) == 0.0

    def test_unordered_gold_ignores_order(self, tiny_db):
        gold = "SELECT concert_name FROM concert"
        pred = "SELECT concert_name FROM concert ORDER BY concert_name DESC"
        assert score_correctness(pred, gold, tiny_db) == 1.0


class TestDegenerate:
    def test_normal_output_unpenalized(self):
        assert score_degenerate("SELECT a FROM t WHERE x = 1") == 0.0

    def test_empty_is_worst(self):
        assert score_degenerate("   ") == -1.0

    def test_overlong_penalized(self):
        assert score_degenerate("SELECT " + "a, " * 600) <= -0.5

    def test_repetition_collapse_penalized(self):
        assert score_degenerate("go " * 50) <= -0.5


class TestTRLAdapters:
    def test_shapes_and_weighting(self, tiny_db: Path):
        funcs = make_reward_funcs(db_root=tiny_db.parent.parent)
        completions = ["SELECT count(*) FROM concert", "garbage"]
        db_id = ["concert_db", "concert_db"]
        gold = [GOLD, GOLD]
        fmt, exe, cor, deg = (
            funcs[0](completions),
            funcs[1](completions, db_id=db_id),
            funcs[2](completions, db_id=db_id, gold=gold),
            funcs[3](completions),
        )
        assert fmt == [0.2, 0.0]
        assert exe == [0.3, 0.0]
        assert cor == [1.0, 0.0]
        assert deg == [0.0, 0.0]
