# backend/Dockerfile
# Build context is the repository root (see docker-compose.yaml) because this
# is a uv workspace: resolving the locked backend package requires every
# member's pyproject.toml alongside the shared uv.lock.

FROM python:3.11-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.11 /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

# Workspace metadata only; no application source yet, so dependency layers
# stay cached across source-only changes.
COPY pyproject.toml uv.lock .python-version ./
COPY backend/pyproject.toml backend/pyproject.toml
RUN uv sync --locked --package backend --no-dev

FROM python:3.11-slim
WORKDIR /app

# The venv lives outside /app so it survives the docker-compose dev bind
# mount of ./backend onto /app.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1

COPY backend ./

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
