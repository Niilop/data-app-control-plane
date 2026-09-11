# backend/main.py
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from api.endpoints import example, llm, auth, data, rag, chat, jobs
from core.config import Settings, get_settings
from core.rate_limit import limiter
from core.database import get_db

# Create all database tables
# Base.metadata.create_all(bind=engine)

# Load settings once at startup
settings = get_settings()

app = FastAPI(title="DS POC API")

# Register the limiter to the FastAPI app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# Include routes
app.include_router(auth.router)
app.include_router(example.router)
app.include_router(llm.router)
app.include_router(data.router)
app.include_router(rag.router)
app.include_router(chat.router)
app.include_router(jobs.router)

# Root endpoint
@app.get("/")
def root(settings: Settings = Depends(get_settings)):
    """Returns a basic health message."""
    return {"message": f"{settings.app_name} is running"}


# Health check
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return {"uptime": "todo", "requests": 0}