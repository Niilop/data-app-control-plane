from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


# ============= Example Schemas =============
class ExampleRequest(BaseModel):
    name: str
    task: str


class ExampleResponse(BaseModel):
    result: str


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
