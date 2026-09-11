from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ============= Example Schemas =============
class ExampleRequest(BaseModel):
    name: str
    task: str


class ExampleResponse(BaseModel):
    result: str


# ============= Auth Schemas =============
class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must fit within 72 UTF-8 bytes")
        return value


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
    is_active: bool
    is_platform_admin: bool

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
