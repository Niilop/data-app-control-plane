# FastAPI LLM Template

A modular FastAPI backend template for building LLM-powered applications with RAG, persistent chat, async jobs, and multi-provider AI support.

---

## Features

### Authentication
- JWT-based login (HS256, configurable expiry)
- User registration with bcrypt password hashing
- Login via email or username
- Protected routes via `Depends(get_current_user)`

### Retrieval-Augmented Generation (RAG)
- Document ingestion with automatic chunking (RecursiveCharacterTextSplitter)
- Vector embeddings via Google Gemini (768-dim, stored in pgvector)
- Cosine similarity retrieval from PostgreSQL
- Sync (`POST /rag/ingest`) and async (`POST /rag/ingest/async`) ingestion
- LLM-powered query answering with retrieved context
- Per-user document isolation

### Persistent Chat
- Multi-turn conversation threading
- Full message history stored per conversation
- System prompt support
- Conversation lifecycle: create, continue, list, delete

### Async Background Jobs
- UUID-based job tracking
- States: `PENDING → RUNNING → COMPLETED / FAILED`
- Poll job status via `GET /jobs/{job_id}`
- Used for non-blocking RAG ingestion

### LLM Integration
- Multi-provider support: **Gemini**, **OpenAI**, **Anthropic**
- Runtime provider selection via `LLM_PROVIDER` env var
- Streaming text summarization (SSE)
- LangChain abstraction for easy provider swapping

### Data Management
- CSV upload with validation (10 MB max, 10 datasets per user)
- Automatic metadata extraction
- Persistent catalog with timestamps

### Rate Limiting
- slowapi-based throttling per endpoint
- Returns HTTP 429 when exceeded

### Frontend
- Streamlit UI with login/register, chat interface, and API testing

---

## Project Structure

```
Template/
├── backend/
│   ├── api/endpoints/
│   │   ├── auth.py           # Registration, login, /me
│   │   ├── chat.py           # Conversation threading
│   │   ├── rag.py            # Document ingestion & querying
│   │   ├── jobs.py           # Async job status
│   │   ├── llm.py            # Summarization (streaming)
│   │   ├── data.py           # CSV upload & catalog
│   │   └── example.py        # Template endpoint
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── rag_service.py
│   │   ├── chat_service.py
│   │   ├── job_service.py
│   │   ├── llm_service.py
│   │   └── data_service.py
│   ├── models/
│   │   ├── database.py       # SQLAlchemy ORM models
│   │   └── schemas.py        # Pydantic schemas
│   ├── core/
│   │   ├── config.py         # Settings & env vars
│   │   ├── database.py       # DB engine & session
│   │   ├── rate_limit.py
│   │   └── logging.py
│   ├── alembic/versions/
│   │   ├── 001_initial.py
│   │   ├── 002_add_document_chunks.py
│   │   ├── 003_add_chat_threads.py
│   │   └── 004_add_background_jobs.py
│   ├── main.py
│   ├── requirements.txt      # used by backend/Dockerfile
│   └── pyproject.toml        # used by uv for local (non-Docker) dev
├── frontend/
│   ├── app.py                # Streamlit UI
│   ├── requirements.txt      # used by frontend/Dockerfile
│   └── pyproject.toml        # used by uv for local (non-Docker) dev
├── tests/
│   ├── test_auth.py
│   └── test_rag_service.py
├── data/
│   ├── raw/
│   ├── processed/
│   └── external/
├── docker-compose.yaml
├── pyproject.toml            # uv workspace root (backend + frontend)
├── uv.lock
└── .env.example
```

---

## Architecture

```
Client
  ↓
FastAPI Route  (api/endpoints/)
  ↓
Pydantic Schema  (validation)
  ↓
Service Layer  (business logic)
  ↓
PostgreSQL / pgvector / LLM Provider
  ↓
JSON Response
```

### Database Schema

| Table | Key Columns |
|---|---|
| `users` | email, username, password_hash |
| `conversations` | user_id, title |
| `messages` | conversation_id, role, content |
| `document_chunks` | user_id, source, content, embedding (768-dim) |
| `background_jobs` | id (UUID), job_type, status, result, error |
| `data_catalogs` | user_id, name, file_path, metadata |

---

## Getting Started

### 1. Configure environment

```bash
cp .env.example .env
# Fill in: DATABASE_URL, LLM_PROVIDER, GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY, JWT_SECRET_KEY
```

### 2. Start services

```bash
docker-compose up --build
```

This starts:
- `db` — PostgreSQL 16 with pgvector (port 5432)
- `backend` — FastAPI + Uvicorn with hot reload (port 8000)
- `frontend` — Streamlit UI (port 8501)

### 3. Apply migrations

```bash
cd backend
alembic upgrade head
```

---

## Local Development (without Docker)

Dependencies are managed with [`uv`](https://docs.astral.sh/uv/) via the workspace `pyproject.toml` / `uv.lock` at the repo root — this is cross-platform and works the same on Windows, macOS, and Linux/WSL. `requirements.txt` files are kept alongside for the Docker images and stay in sync manually when dependencies change.

```bash
# From the repo root — installs both backend and frontend into .venv/
uv sync

# Run the backend
cd backend
uv run uvicorn main:app --reload

# Run the frontend (separate terminal)
cd frontend
uv run streamlit run app.py
```

You'll still need Postgres/pgvector reachable at `DATABASE_URL` — either run `docker-compose up db` for just the database, or point `DATABASE_URL` at a local Postgres instance.

---

## API Endpoints

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Get JWT token |
| GET | `/auth/me` | Current user info |

### Chat
| Method | Path | Description |
|---|---|---|
| POST | `/chat/conversations` | Create conversation |
| GET | `/chat/conversations` | List conversations |
| POST | `/chat/conversations/{id}/messages` | Send message |
| GET | `/chat/conversations/{id}/messages` | Get history |
| DELETE | `/chat/conversations/{id}` | Delete conversation |

### RAG
| Method | Path | Description |
|---|---|---|
| POST | `/rag/ingest` | Ingest document (sync) |
| POST | `/rag/ingest/async` | Ingest document (async job) |
| POST | `/rag/query` | Query with retrieval |

### Jobs
| Method | Path | Description |
|---|---|---|
| GET | `/jobs/{job_id}` | Poll job status |

### LLM
| Method | Path | Description |
|---|---|---|
| POST | `/llm/summarize` | Streaming summarization |

### Data
| Method | Path | Description |
|---|---|---|
| POST | `/data/upload` | Upload CSV |
| GET | `/data/catalog` | List datasets |

### System
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/metrics` | Basic metrics |
| GET | `/docs` | Swagger UI |

---

## Database Migrations

```bash
# Create a new migration after changing models/database.py
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

---

## Testing

```bash
# Run test suite
pytest tests/

# Or use the REST client examples
# tests/test.http (VS Code REST Client)
```

---

## LLM Provider Configuration

Set `LLM_PROVIDER` in `.env` to switch providers at runtime:

| Value | Provider | Required Key |
|---|---|---|
| `gemini` | Google Gemini | `GEMINI_API_KEY` |
| `openai` | OpenAI | `OPENAI_API_KEY` |
| `anthropic` | Anthropic | `ANTHROPIC_API_KEY` |

---

## Purpose

This template is a starting point for building:
- LLM-powered chat applications
- RAG systems with persistent vector storage
- Data pipelines with async processing
- Multi-tenant AI backends

It is intentionally **modular**: swap providers, add endpoints, or extend the service layer without restructuring the project.
