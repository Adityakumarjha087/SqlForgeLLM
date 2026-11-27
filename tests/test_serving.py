import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tiny_db, monkeypatch):
    """App wired to the mock backend and the tiny fixture database."""
    monkeypatch.setenv("SQLFORGE_BACKEND", "mock")
    monkeypatch.setenv("SQLFORGE_DB_ROOT", str(tiny_db.parent.parent))
    monkeypatch.setenv("SQLFORGE_RATE_LIMIT_PER_MINUTE", "5")
    import importlib

    from sqlforge.serving import app as app_module

    importlib.reload(app_module)
    app_module.db_root = tiny_db.parent.parent
    return TestClient(app_module.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["backend"] == "mock"
    # The frontend reads its question-length cap from here.
    assert body["max_question_chars"] > 0


def test_databases_lists_fixture(client):
    assert client.get("/databases").json() == {"databases": ["concert_db"]}


def test_schema_endpoint(client):
    response = client.get("/schema/concert_db")
    assert response.status_code == 200
    assert "CREATE TABLE" in response.json()["schema"]


def test_schema_unknown_db_404(client):
    response = client.get("/schema/nope")
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


@pytest.mark.parametrize("question", ["", "   ", "\n\t "])
def test_blank_question_rejected(client, question):
    response = client.post("/query", json={"question": question, "db_id": "concert_db"})
    assert response.status_code == 422


def test_generate_sql(client):
    response = client.post(
        "/generate-sql", json={"question": "How many concerts?", "db_id": "concert_db"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sql"].upper().startswith("SELECT")
    assert body["latency_ms"] >= 0


def test_query_executes(client):
    response = client.post("/query", json={"question": "How many concerts?", "db_id": "concert_db"})
    assert response.status_code == 200
    body = response.json()
    assert body["execution_error"] is None
    assert body["rows"] == [[3]]  # mock counts rows of first table (concert)


def test_unknown_db_404(client):
    response = client.post("/generate-sql", json={"question": "hi", "db_id": "nope"})
    assert response.status_code == 404


def test_path_traversal_rejected(client):
    response = client.post("/generate-sql", json={"question": "hi", "db_id": "../etc"})
    assert response.status_code == 422  # fails pydantic pattern before touching disk


def test_question_length_capped(client):
    response = client.post("/generate-sql", json={"question": "x" * 10_000, "db_id": "concert_db"})
    assert response.status_code == 422


def test_rate_limit_kicks_in(client):
    payload = {"question": "How many concerts?", "db_id": "concert_db"}
    codes = [client.post("/generate-sql", json=payload).status_code for _ in range(8)]
    assert 429 in codes
    assert codes[0] == 200


def test_rate_limit_response_says_when_to_retry(client):
    payload = {"question": "How many concerts?", "db_id": "concert_db"}
    responses = [client.post("/generate-sql", json=payload) for _ in range(8)]
    limited = next(r for r in responses if r.status_code == 429)
    assert int(limited.headers["Retry-After"]) >= 1


def test_databases_graceful_without_data_dir(client, tmp_path):
    from sqlforge.serving import app as app_module

    app_module.db_root = tmp_path / "does-not-exist"
    body = client.get("/databases").json()
    assert body["databases"] == []
    assert "hint" in body


def test_query_reports_unsafe_generated_sql_without_running_it(client, tiny_db):
    from sqlforge.serving import app as app_module
    from sqlforge.serving.backends import Generation

    class DeletingBackend:
        def generate(self, schema, question):
            return Generation(sql="DELETE FROM concert", completion_tokens=3)

    app_module._backend = DeletingBackend()
    response = client.post("/query", json={"question": "Remove everything", "db_id": "concert_db"})
    assert response.status_code == 200
    body = response.json()
    assert body["sql"] == "DELETE FROM concert"
    assert body["execution_error"]
    assert body["rows"] == []
    # The sandbox refused it, so the data is untouched.
    with sqlite3.connect(tiny_db) as conn:
        assert conn.execute("SELECT count(*) FROM concert").fetchone() == (3,)
