from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, Uuid
from sqlmodel import JSON, Column, Field, SQLModel


class ManagedComponentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class ManagedComponentBundle(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "managed_component_bundle"
    __table_args__ = (
        UniqueConstraint("bundle_name"),
        Index("ix_managed_component_bundle_bundle_name", "bundle_name"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    bundle_name: str = Field(max_length=64)
    extension_id: str = Field(max_length=128)
    version: str = Field(default="0.0.0", max_length=64)
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    components: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    source_hash: str = Field(max_length=64)
    archive_path: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(default=ManagedComponentStatus.ACTIVE.value, index=True, max_length=16)
    error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    uploaded_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
