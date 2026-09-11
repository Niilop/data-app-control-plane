from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends
from langchain_core.prompts import PromptTemplate
from sqlalchemy.orm import Session

from api.endpoints.auth import get_current_user
from core.database import get_db
from core.rate_limit import limiter
from models.database import User
from models.schemas import (
    DocumentIngestRequest,
    DocumentIngestResponse,
    JobSubmitResponse,
    RAGQueryRequest,
    RAGQueryResponse,
)
from services.job_service import create_job, run_job
from services.llm_service import llm
from services.rag_service import ingest_document, retrieve_chunks

router = APIRouter(prefix="/rag", tags=["RAG"])

_rag_prompt = PromptTemplate.from_template(
    "Answer the question using only the context below. "
    "If the context does not contain enough information, say so.\n\n"
    "Context:\n{context}\n\n"
    "Question: {question}\n\n"
    "Answer:"
)


@router.post("/ingest", response_model=DocumentIngestResponse)
@limiter.limit("20/minute")
def ingest(
    request: Request,
    body: DocumentIngestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chunk, embed, and store a document for later retrieval."""
    try:
        n = ingest_document(db, current_user.id, body.source, body.text)
        return DocumentIngestResponse(source=body.source, chunks_created=n)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/async", response_model=JobSubmitResponse)
@limiter.limit("20/minute")
def ingest_async(
    request: Request,
    body: DocumentIngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a document for background embedding. Returns a job_id to poll via GET /jobs/{job_id}."""
    job = create_job(db, current_user.id, "rag_ingest")
    source, text, user_id = body.source, body.text, current_user.id
    background_tasks.add_task(
        run_job,
        job.id,
        lambda bg_db: {"source": source, "chunks_created": ingest_document(bg_db, user_id, source, text)},
    )
    return JobSubmitResponse(job_id=job.id, status=job.status)


@router.post("/query", response_model=RAGQueryResponse)
@limiter.limit("10/minute")
def query(
    request: Request,
    body: RAGQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve relevant chunks and answer the question with the configured LLM."""
    chunks = retrieve_chunks(db, current_user.id, body.question, k=body.top_k)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No documents found. Ingest some documents first via POST /rag/ingest.",
        )

    context = "\n\n---\n\n".join(c.content for c in chunks)
    chain = _rag_prompt | llm
    response = chain.invoke({"context": context, "question": body.question})

    return RAGQueryResponse(
        answer=response.content,
        sources=list(dict.fromkeys(c.source for c in chunks)),  # dedup, preserve order
        chunks=[c.content for c in chunks],
    )
