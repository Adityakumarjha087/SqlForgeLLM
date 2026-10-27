from sqlforge.eval.metrics import (
    canonical_sql,
    exact_match,
    has_top_level_order_by,
    rows_match,
    score_prediction,
)


class TestRowsMatch:
    def test_order_insensitive_same_multiset(self):
        assert rows_match([(1,), (2,)], [(2,), (1,)], order_sensitive=False)

    def test_order_sensitive_detects_wrong_order(self):
        assert not rows_match([(1,), (2,)], [(2,), (1,)], order_sensitive=True)

    def test_duplicates_are_multiset_not_set(self):
        # SELECT DISTINCT vs SELECT must not be conflated.
        assert not rows_match([(1,), (1,), (2,)], [(1,), (2,)], order_sensitive=False)

    def test_nulls_compare_equal(self):
        assert rows_match([(None, "a")], [(None, "a")], order_sensitive=False)
        assert not rows_match([(None,)], [(0,)], order_sensitive=False)

    def test_float_rounding_absorbs_representation_noise(self):
        assert rows_match([(0.1 + 0.2,)], [(0.3,)], order_sensitive=False)


class TestOrderByDetection:
    def test_top_level_order_by(self):
        assert has_top_level_order_by("SELECT a FROM t ORDER BY a")

    def test_no_order_by(self):
        assert not has_top_level_order_by("SELECT a FROM t")

    def test_subquery_order_by_is_not_top_level(self):
        sql = "SELECT * FROM (SELECT a FROM t ORDER BY a LIMIT 3)"
        assert not has_top_level_order_by(sql)


class TestExactMatch:
    def test_whitespace_and_case_insensitive(self):
        assert exact_match("select  A from T", "SELECT a FROM t")

    def test_different_queries_differ(self):
        assert not exact_match("SELECT a FROM t", "SELECT b FROM t")

    def test_canonical_survives_unparseable(self):
        assert canonical_sql("not sql at all") == "not sql at all"


class TestScorePrediction:
    def test_correct_prediction(self, tiny_db):
        s = score_prediction(
            tiny_db,
            gold_sql="SELECT count(*) FROM concert",
            pred_sql="SELECT COUNT(*) FROM concert",
        )
        assert s.execution_match
        assert s.exact_match

    def test_equivalent_but_not_exact(self, tiny_db):
        s = score_prediction(
            tiny_db,
            gold_sql="SELECT name FROM stadium WHERE capacity > 1000",
            pred_sql="SELECT name FROM stadium WHERE capacity >= 1001",
        )
        assert s.execution_match
        assert not s.exact_match

    def test_wrong_result_fails(self, tiny_db):
        s = score_prediction(
            tiny_db,
            gold_sql="SELECT count(*) FROM concert",
            pred_sql="SELECT count(*) FROM stadium",
        )
        assert not s.execution_match

    def test_pred_error_recorded(self, tiny_db):
        s = score_prediction(
            tiny_db,
            gold_sql="SELECT count(*) FROM concert",
            pred_sql="SELECT nope FROM nowhere",
        )
        assert not s.execution_match
        assert s.pred_error

    def test_order_by_gold_requires_order(self, tiny_db):
        s = score_prediction(
            tiny_db,
            gold_sql="SELECT concert_name FROM concert ORDER BY year",
            pred_sql="SELECT concert_name FROM concert ORDER BY year DESC",
        )
        assert not s.execution_match
