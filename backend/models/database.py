# backend/models/database.py
import enum
from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    false,
    true,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Compatibility constant imported by historical migration 002. No runtime embeddings.
EMBEDDING_DIM = 768


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    settings: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)

    # Relationships
    data_catalogs = relationship(
        "DataCatalog", back_populates="owner", cascade="all, delete-orphan"
    )
    pipelines = relationship(
        "Pipeline", back_populates="owner", cascade="all, delete-orphan"
    )


class DataCatalog(Base):
    __tablename__ = "data_catalogs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    description = Column(Text, default="")
    data_metadata = Column(JSON, default={})  # Store shape, columns, data types, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    owner = relationship("User", back_populates="data_catalogs")


class PipelineStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    COMPLETED = "completed"
    FAILED = "failed"


class Pipeline(Base):
    __tablename__ = "pipelines"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    pipeline_type = Column(
        String(100), nullable=False
    )  # e.g., "news_scraper", "data_processor"
    description = Column(Text, default="")
    status = Column(SQLEnum(PipelineStatus), default=PipelineStatus.INACTIVE)
    schedule = Column(String(100), default="")  # e.g., "0 0 * * *" for cron
    pipeline_config = Column(JSON, default={})  # Store pipeline-specific configuration
    last_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    owner = relationship("User", back_populates="pipelines")
