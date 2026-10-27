# SQLForge API image (CPU; the model backend is chosen by SQLFORGE_BACKEND).
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
# ml group gives the transformers backend; mock needs nothing extra.
RUN uv sync --frozen --no-install-project --group ml

COPY src ./src
COPY configs ./configs
COPY scripts ./scripts
RUN uv sync --frozen --group ml

# Spider databases are mounted, not baked in (they are 1GB+ with test DBs):
#   docker run -v ./data:/app/data ...
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "sqlforge.serving.app:app", "--host", "0.0.0.0", "--port", "8000"]
