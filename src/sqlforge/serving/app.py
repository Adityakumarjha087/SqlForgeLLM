"""FastAPI app: natural-language question -> SQL (and optionally its result rows).

Security posture:
- generated SQL is executed only through the safe executor (read-only, single
  SELECT, timeout, row cap) - the model's output is never trusted
- db_id is validated against the databases that actually exist (no paths)
- question length is capped; per-IP token-bucket rate limiting

Run: uv run uvicorn sqlforge.serving.app:app --port 8000
Backend/model come from configs/serve.yaml (override via SQLFORGE_* env vars,
e.g. SQLFORGE_BACKEND=mock for frontend development without a model).
"""

import threading
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from sqlforge.config import load_config
from sqlforge.data.schema import extract_schema
from sqlforge.execution import execute_sql
from sqlforge.serving.backends import ModelBackend, make_backend

REPO_ROOT = Path(__file__).resolve().parents[3]


class ServeConfig(BaseModel):
    backend: str
    model_id: str
    adapter: str
    ollama_model: str
    ollama_url: str
    db_root: str
    max_new_tokens: int
    max_question_chars: int
    exec_timeout_s: float
    exec_row_limit: int
    rate_limit_per_minute: int


class GenerateRequest(BaseModel):
    question: str = Field(min_length=1)
    db_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_]+$")


class GenerateResponse(BaseModel):
    sql: str
    latency_ms: float
    tokens_per_second: float | None = None


class QueryResponse(GenerateResponse):
    columns: list[str]
    rows: list[list]
    truncated: bool
    execution_error: str | None = None


class TokenBucket:
    """Minimal per-key rate limiter: `per_minute` requests, refilled continuously."""

    def __init__(self, per_minute: int):
        self.rate = per_minute / 60.0
        self.capacity = float(per_minute)
        self.state: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            tokens, last = self.state.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < 1.0:
                self.state[key] = (tokens, now)
                return False
            self.state[key] = (tokens - 1.0, now)
            return True


cfg = load_config(REPO_ROOT / "configs" / "serve.yaml", ServeConfig)
db_root = REPO_ROOT / cfg.db_root
bucket = TokenBucket(cfg.rate_limit_per_minute)
_backend: ModelBackend | None = None

app = FastAPI(title="SQLForge", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_backend() -> ModelBackend:
    global _backend
    if _backend is None:
        _backend = make_backend(cfg)
    return _backend


@lru_cache(maxsize=256)
def get_schema(db_id: str) -> str:
    return extract_schema(db_path(db_id))


def db_path(db_id: str) -> Path:
    return db_root / db_id / f"{db_id}.sqlite"


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith(("/generate-sql", "/query")):
        client = request.client.host if request.client else "unknown"
        if not bucket.allow(client):
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "backend": cfg.backend}


@app.get("/databases")
def databases() -> dict:
    """Available db_ids and their schemas (drives the frontend's picker)."""
    if not db_root.is_dir():
        # Fresh checkout without Spider data: answer instead of 500ing.
        return {
            "databases": [],
            "hint": "no databases found - run scripts/download_spider.py and mount data/",
        }
    ids = sorted(p.name for p in db_root.iterdir() if (p / f"{p.name}.sqlite").exists())
    return {"databases": ids}


@app.get("/schema/{db_id}")
def schema(db_id: str) -> dict:
    _validate_db(db_id)
    return {"db_id": db_id, "schema": get_schema(db_id)}


def _validate_db(db_id: str) -> None:
    if not db_id.replace("_", "").isalnum() or not db_path(db_id).exists():
        raise HTTPException(status_code=404, detail=f"unknown db_id: {db_id}")


def _generate(request: GenerateRequest) -> tuple[str, float, float | None]:
    if len(request.question) > cfg.max_question_chars:
        raise HTTPException(
            status_code=422, detail=f"question longer than {cfg.max_question_chars} chars"
        )
    _validate_db(request.db_id)
    start = time.monotonic()
    generation = get_backend().generate(get_schema(request.db_id), request.question)
    latency = time.monotonic() - start
    tps = generation.completion_tokens / latency if generation.completion_tokens else None
    return generation.sql, latency * 1000, tps


@app.post("/generate-sql", response_model=GenerateResponse)
def generate_sql(request: GenerateRequest) -> GenerateResponse:
    sql, latency_ms, tps = _generate(request)
    return GenerateResponse(sql=sql, latency_ms=latency_ms, tokens_per_second=tps)


@app.post("/query", response_model=QueryResponse)
def query(request: GenerateRequest) -> QueryResponse:
    sql, latency_ms, tps = _generate(request)
    result = execute_sql(
        db_path(request.db_id),
        sql,
        timeout_s=cfg.exec_timeout_s,
        row_limit=cfg.exec_row_limit,
    )
    return QueryResponse(
        sql=sql,
        latency_ms=latency_ms,
        tokens_per_second=tps,
        columns=result.columns,
        rows=[list(r) for r in result.rows],
        truncated=result.truncated,
        execution_error=result.error,
    )
