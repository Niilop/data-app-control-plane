from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

# ============= Example Schemas =============
class ExampleRequest(BaseModel):
    name: str
    task: str


class ExampleResponse(BaseModel):
    result: str


# ============= LLM Schemas =============
class SummaryRequest(BaseModel):
    text: str


class SummaryResponse(BaseModel):
    summary: str


# ============= Auth Schemas =============
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    created_at: datetime
    settings: dict = {}

    class Config:
        from_attributes = True


# ============= Data Catalog Schemas =============
class DataCatalogCreate(BaseModel):
    name: str
    file_path: str
    description: Optional[str] = ""
    data_metadata: dict = {}


class DataCatalogResponse(BaseModel):
    id: int
    name: str
    file_path: str
    description: str
    data_metadata: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============= Model Schemas =============
class ModelCreate(BaseModel):
    name: str
    model_type: str
    description: Optional[str] = ""
    file_path: str
    dataset_ids: list = []
    metrics: dict = {}


class ModelResponse(BaseModel):
    id: int
    name: str
    model_type: str
    description: str
    file_path: str
    dataset_ids: list
    metrics: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============= RAG Schemas =============
class DocumentIngestRequest(BaseModel):
    source: str          # label for this document (e.g. filename)
    text: str            # full document text to chunk and embed


class DocumentIngestResponse(BaseModel):
    source: str
    chunks_created: int


class RAGQueryRequest(BaseModel):
    question: str
    top_k: int = 4       # number of chunks to retrieve


class RAGQueryResponse(BaseModel):
    answer: str
    sources: List[str]   # deduplicated source labels
    chunks: List[str]    # raw retrieved chunks


# ============= Chat Schemas =============
class ChatMessageRequest(BaseModel):
    message: str
    title: Optional[str] = None   # only used when creating a new conversation


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True


class ConversationSummary(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatReply(BaseModel):
    conversation_id: int
    message_id: int    # DB id of the saved assistant message
    reply: str


# ============= Background Job Schemas =============
class JobSubmitResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm_job(cls, job) -> "JobStatusResponse":
        return cls(
            job_id=job.id,
            job_type=job.job_type,
            status=job.status.value if hasattr(job.status, "value") else job.status,
            result=job.result,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


# ============= Pipeline Schemas =============
class PipelineCreate(BaseModel):
    name: str
    pipeline_type: str
    description: Optional[str] = ""
    status: str = "inactive"
    schedule: Optional[str] = ""
    pipeline_config: dict = {}


class PipelineResponse(BaseModel):
    id: int
    name: str
    pipeline_type: str
    description: str
    status: str
    schedule: str
    pipeline_config: dict
    last_run: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True