from sqlforge.analysis import accuracy_by_category, categorize, difficulty


class TestCategorize:
    def test_join(self):
        assert "join" in categorize("SELECT * FROM a JOIN b ON a.id = b.id")

    def test_group_by_and_aggregation(self):
        feats = categorize("SELECT x, count(*) FROM t GROUP BY x")
        assert {"group_by", "aggregation"} <= feats

    def test_nested(self):
        assert "nested" in categorize("SELECT * FROM t WHERE x IN (SELECT y FROM u)")

    def test_order_limit(self):
        assert "order_limit" in categorize("SELECT * FROM t ORDER BY x LIMIT 5")
        assert "order_limit" in categorize("SELECT * FROM t LIMIT 5")

    def test_set_op(self):
        assert "set_op" in categorize("SELECT a FROM t UNION SELECT a FROM u")

    def test_simple_query_has_no_features(self):
        assert categorize("SELECT a FROM t") == set()


class TestDifficulty:
    def test_simple_is_easy(self):
        assert difficulty("SELECT a FROM t") == "easy"

    def test_monotonic_with_complexity(self):
        order = ["easy", "medium", "hard", "extra"]
        simple = difficulty("SELECT a FROM t")
        heavy = difficulty(
            "SELECT a, count(*) FROM t JOIN u ON t.i = u.i JOIN v ON u.j = v.j "
            "WHERE t.x IN (SELECT x FROM w WHERE y > 1 ORDER BY x) "
            "GROUP BY a ORDER BY count(*) UNION SELECT b, 0 FROM z"
        )
        assert order.index(simple) < order.index(heavy)
        assert heavy == "extra"


class TestAccuracyByCategory:
    def test_buckets_and_rates(self):
        preds = [
            {"gold": "SELECT a FROM t", "execution_match": True},
            {"gold": "SELECT a FROM t JOIN u ON t.i = u.i", "execution_match": False},
            {"gold": "SELECT count(*) FROM t", "execution_match": True},
        ]
        result = accuracy_by_category(preds)
        assert result["overall"] == {"n": 3, "accuracy": 2 / 3}
        assert result["join"] == {"n": 1, "accuracy": 0.0}
        assert result["aggregation"] == {"n": 1, "accuracy": 1.0}
        assert result["set_op"]["n"] == 0
