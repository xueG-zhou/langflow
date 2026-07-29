"""Administrator-managed component bundles."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlmodel import col, select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.interface.components import get_and_cache_all_types_dict
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.managed_component import ManagedComponentBundle, ManagedComponentStatus
from langflow.services.deps import get_settings_service
from langflow.services.managed_components import (
    MAX_ARCHIVE_BYTES,
    disable_component_bundle,
    install_component_bundle,
    read_bundle_source,
    refresh_managed_components,
)
from langflow.utils.i18n import translate_component_dict

router = APIRouter(prefix="/managed-components", tags=["Managed Components"])


class ComponentMetadata(BaseModel):
    namespaced_id: str
    class_name: str
    display_name: str
    description: str = ""
    documentation: str | None = None
    icon: str | None = None
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)


class ManagedComponentSummary(BaseModel):
    id: str | UUID
    bundle_name: str
    extension_id: str
    version: str
    description: str | None
    components: list[ComponentMetadata]
    status: str
    origin: str = "MANAGED"
    can_disable: bool = True
    error: str | None
    uploaded_by: UUID | None
    created_at: datetime | None
    updated_at: datetime | None


class FlowUsage(BaseModel):
    id: UUID
    name: str
    node_count: int


class ManagedComponentDetail(ManagedComponentSummary):
    source_code: str
    usage_count: int
    usages: list[FlowUsage]


def _require_superuser(user) -> None:
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Component management requires an administrator"
        )


def _summary(row: ManagedComponentBundle) -> ManagedComponentSummary:
    return ManagedComponentSummary.model_validate(row, from_attributes=True)


def _template_fields(template: dict[str, Any]) -> list[dict[str, Any]]:
    fields = template.get("template")
    if not isinstance(fields, dict):
        return []
    return [{"name": name, **field} for name, field in fields.items() if isinstance(field, dict) and name != "code"]


def _system_component(class_name: str, template: dict[str, Any]) -> ComponentMetadata:
    namespaced_id = template.get("namespaced_id")
    return ComponentMetadata(
        namespaced_id=namespaced_id if isinstance(namespaced_id, str) else class_name,
        class_name=class_name,
        display_name=str(template.get("display_name") or class_name),
        description=str(template.get("description") or ""),
        documentation=template.get("documentation") if isinstance(template.get("documentation"), str) else None,
        icon=template.get("icon") if isinstance(template.get("icon"), str) else None,
        inputs=_template_fields(template),
        outputs=template.get("outputs") if isinstance(template.get("outputs"), list) else [],
    )


async def _system_summaries(
    managed_rows: list[ManagedComponentBundle],
    locale: str,
) -> list[ManagedComponentSummary]:
    all_types = await get_and_cache_all_types_dict(settings_service=get_settings_service())
    if locale != "en":
        all_types = translate_component_dict(all_types, locale)
    managed_identifiers = {
        identifier
        for row in managed_rows
        for component in row.components
        for identifier in (component.get("namespaced_id"), component.get("class_name"))
        if isinstance(identifier, str)
    }
    summaries: list[ManagedComponentSummary] = []
    for category, templates in sorted(all_types.items()):
        if not isinstance(templates, dict):
            continue
        components = [
            _system_component(class_name, template)
            for class_name, template in sorted(templates.items())
            if isinstance(template, dict)
            and class_name not in managed_identifiers
            and template.get("namespaced_id") not in managed_identifiers
        ]
        if components:
            summaries.append(
                ManagedComponentSummary(
                    id=f"system:{category}",
                    bundle_name=category,
                    extension_id="langflow",
                    version="built-in",
                    description=None,
                    components=components,
                    status="ACTIVE",
                    origin="SYSTEM",
                    can_disable=False,
                    error=None,
                    uploaded_by=None,
                    created_at=None,
                    updated_at=None,
                )
            )
    return summaries


def _node_uses_component(node: dict, identifiers: set[str]) -> bool:
    try:
        serialized = json.dumps(node, default=str)
    except (TypeError, ValueError):
        return False
    return any(identifier in serialized for identifier in identifiers)


async def _find_usages(session: DbSession, row: ManagedComponentBundle) -> list[FlowUsage]:
    identifiers = {
        identifier
        for component in row.components
        for identifier in (component.get("namespaced_id"), component.get("class_name"))
        if isinstance(identifier, str) and identifier
    }
    if not identifiers:
        return []

    flows = list(await session.exec(select(Flow)))
    usages: list[FlowUsage] = []
    for flow in flows:
        nodes = (flow.data or {}).get("nodes", [])
        node_count = sum(1 for node in nodes if isinstance(node, dict) and _node_uses_component(node, identifiers))
        if node_count:
            usages.append(FlowUsage(id=flow.id, name=flow.name, node_count=node_count))
    return usages


@router.get("", response_model=list[ManagedComponentSummary])
@router.get("/", response_model=list[ManagedComponentSummary])
async def list_managed_components(
    request: Request,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> list[ManagedComponentSummary]:
    _require_superuser(current_user)
    statement = select(ManagedComponentBundle).order_by(col(ManagedComponentBundle.updated_at).desc())
    managed_rows = list(await session.exec(statement))
    locale = getattr(request.state, "locale", "en")
    system_rows = await _system_summaries(managed_rows, locale)
    return [*system_rows, *[_summary(row) for row in managed_rows]]


@router.post("", response_model=ManagedComponentSummary, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ManagedComponentSummary, status_code=status.HTTP_201_CREATED)
async def upload_managed_component(
    current_user: CurrentActiveUser,
    session: DbSession,
    file: Annotated[UploadFile, File(description="A ZIP archive containing one component bundle")],
) -> ManagedComponentSummary:
    _require_superuser(current_user)
    settings_service = get_settings_service()
    if not settings_service.settings.allow_custom_components:
        raise HTTPException(status_code=403, detail="Custom component creation is disabled")

    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Only ZIP archives can be uploaded")
    if file.size is not None and file.size > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="The component ZIP archive must be 25 MB or smaller")
    contents = await file.read(MAX_ARCHIVE_BYTES + 1)
    if len(contents) > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="The component ZIP archive must be 25 MB or smaller")

    try:
        installed = await asyncio.to_thread(install_component_bundle, contents, filename, settings_service)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = ManagedComponentBundle(**installed, uploaded_by=current_user.id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    try:
        await refresh_managed_components(settings_service)
    except Exception as exc:
        row.status = ManagedComponentStatus.ERROR.value
        row.error = str(exc)
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        await session.commit()
        raise HTTPException(status_code=422, detail=f"Component installed but failed to load: {exc}") from exc
    return _summary(row)


@router.get("/{bundle_id}", response_model=ManagedComponentDetail)
async def get_managed_component(
    bundle_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> ManagedComponentDetail:
    _require_superuser(current_user)
    row = await session.get(ManagedComponentBundle, bundle_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Managed component bundle not found")
    usages = await _find_usages(session, row)
    source_code = await asyncio.to_thread(read_bundle_source, row.archive_path)
    return ManagedComponentDetail(
        **_summary(row).model_dump(),
        source_code=source_code,
        usage_count=len(usages),
        usages=usages,
    )


@router.post("/{bundle_id}/disable", response_model=ManagedComponentSummary)
async def disable_managed_component(
    bundle_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> ManagedComponentSummary:
    _require_superuser(current_user)
    row = await session.get(ManagedComponentBundle, bundle_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Managed component bundle not found")
    if row.status == ManagedComponentStatus.DISABLED.value:
        return _summary(row)

    try:
        destination = await asyncio.to_thread(
            disable_component_bundle,
            row.bundle_name,
            get_settings_service(),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileExistsError, OSError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    row.archive_path = str(destination)
    row.status = ManagedComponentStatus.DISABLED.value
    row.error = None
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await refresh_managed_components(get_settings_service(), removed_bundle=row.bundle_name)
    return _summary(row)
