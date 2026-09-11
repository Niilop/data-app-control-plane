from google import genai
from google.genai import types
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from core.config import get_settings
from models.database import DocumentChunk

settings = get_settings()

EMBEDDING_MODEL = "gemini-embedding-001"

# Use google-genai directly with v1 (stable) API to avoid v1beta 404s.
client = genai.Client(api_key=settings.api_key.get_secret_value())

_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)

# output_dimensionality is required to avoid 2048-dim default and subsequent cosine_distance errors.
def _embed(texts: list[str]) -> list[list[float]]:
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(output_dimensionality=768),
    )
    return [e.values for e in response.embeddings]


def ingest_document(db: Session, user_id: int, source: str, text: str) -> int:
    """Chunk, embed, and store a document. Returns number of chunks created."""
    chunks = _splitter.split_text(text)
    if not chunks:
        return 0

    vectors = _embed(chunks)

    db.add_all(
        DocumentChunk(user_id=user_id, source=source, content=chunk, embedding=vec)
        for chunk, vec in zip(chunks, vectors)
    )
    db.commit()
    return len(chunks)


def retrieve_chunks(db: Session, user_id: int, query: str, k: int = 4) -> list[DocumentChunk]:
    """Embed the query and return the k nearest chunks via cosine distance."""
    query_vector = _embed([query])[0]

    return (
        db.query(DocumentChunk)
        .filter(DocumentChunk.user_id == user_id)
        .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
        .limit(k)
        .all()
    )
