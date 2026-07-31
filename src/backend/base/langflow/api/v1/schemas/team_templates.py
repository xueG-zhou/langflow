from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from langflow.services.database.models.team_template import TeamTemplateVisibility


class TeamTemplateCreate(BaseModel):
    source_flow_id: UUID
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    visibility: TeamTemplateVisibility = TeamTemplateVisibility.PRIVATE

    @field_validator("name")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "Value must not be blank"
            raise ValueError(msg)
        return value


class TeamTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    visibility: TeamTemplateVisibility | None = None
    refresh_from_source: bool = False

    @field_validator("name")
    @classmethod
    def strip_optional_required(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            msg = "Value must not be blank"
            raise ValueError(msg)
        return value


class TeamTemplateSummary(BaseModel):
    id: UUID
    name: str
    description: str | None
    visibility: TeamTemplateVisibility
    icon: str | None
    gradient: str | None
    source_flow_id: UUID | None
    workspace_id: UUID | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    source: str = "team"


class TeamTemplateRead(TeamTemplateSummary):
    flow_data: dict
    schema_version: int
    sanitizer_version: int


class TeamTemplateCreateResponse(TeamTemplateRead):
    cleared_fields: int


class TeamTemplateList(BaseModel):
    items: list[TeamTemplateSummary]
    total: int
    page: int
    page_size: int
