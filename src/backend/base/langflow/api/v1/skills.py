"""API for installing and listing local Skills."""

from __future__ import annotations

import asyncio
import io
import re
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from lfx.services.settings.service import SettingsService
from pydantic import BaseModel

from langflow.api.utils import CurrentActiveUser
from langflow.services.deps import get_settings_service

router = APIRouter(prefix="/skills", tags=["Skills"])

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1000
VALID_SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SkillRead(BaseModel):
    """A Skill installed in Langflow's configuration directory."""

    name: str
    description: str | None = None
    updated_at: datetime


def _skills_directory(settings_service: SettingsService) -> Path:
    config_dir = settings_service.settings.config_dir
    if not config_dir:
        raise HTTPException(status_code=500, detail="Langflow config directory is not configured")
    return Path(config_dir) / "skills"


def _read_frontmatter_value(skill_file: Path, key: str) -> str | None:
    try:
        lines = skill_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    prefix = f"{key}:"
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith(prefix):
            value = line[len(prefix) :].strip().strip("\"'")
            return value or None
    return None


def _list_skills(skills_dir: Path) -> list[SkillRead]:
    if not skills_dir.exists():
        return []
    skills = []
    for directory in skills_dir.iterdir():
        skill_file = directory / "SKILL.md"
        if not directory.is_dir() or not skill_file.is_file():
            continue
        skills.append(
            SkillRead(
                name=_read_frontmatter_value(skill_file, "name") or directory.name,
                description=_read_frontmatter_value(skill_file, "description"),
                updated_at=datetime.fromtimestamp(skill_file.stat().st_mtime, tz=timezone.utc),
            )
        )
    return sorted(skills, key=lambda skill: skill.name.casefold())


def _validated_entries(archive: zipfile.ZipFile) -> tuple[list[zipfile.ZipInfo], str | None]:
    entries = [entry for entry in archive.infolist() if not entry.is_dir()]
    if not entries:
        msg = "The ZIP archive is empty"
        raise ValueError(msg)
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        msg = f"The ZIP archive contains more than {MAX_ARCHIVE_ENTRIES} files"
        raise ValueError(msg)

    total_size = 0
    roots: set[str] = set()
    for entry in entries:
        if "\\" in entry.filename:
            msg = f"Unsafe path in ZIP archive: {entry.filename}"
            raise ValueError(msg)
        path = PurePosixPath(entry.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            msg = f"Unsafe path in ZIP archive: {entry.filename}"
            raise ValueError(msg)
        if stat.S_ISLNK(entry.external_attr >> 16):
            msg = f"Symbolic links are not allowed in Skill archives: {entry.filename}"
            raise ValueError(msg)
        total_size += entry.file_size
        if total_size > MAX_EXTRACTED_BYTES:
            msg = "The extracted Skill is larger than 100 MB"
            raise ValueError(msg)
        roots.add(path.parts[0])

    wrapper = (
        next(iter(roots))
        if len(roots) == 1 and all(len(PurePosixPath(e.filename).parts) > 1 for e in entries)
        else None
    )
    skill_path = f"{wrapper}/SKILL.md" if wrapper else "SKILL.md"
    if not any(PurePosixPath(entry.filename).as_posix() == skill_path for entry in entries):
        msg = "The ZIP archive must contain a SKILL.md file at its root"
        raise ValueError(msg)
    return entries, wrapper


def _install_skill(contents: bytes, archive_name: str, skills_dir: Path) -> SkillRead:
    try:
        archive = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        msg = "The uploaded file is not a valid ZIP archive"
        raise ValueError(msg) from exc

    with archive:
        entries, wrapper = _validated_entries(archive)
        skill_name = wrapper or Path(archive_name).stem
        if not VALID_SKILL_NAME.fullmatch(skill_name):
            msg = "Skill names may only contain letters, numbers, dots, underscores, and hyphens"
            raise ValueError(msg)

        skills_dir.mkdir(parents=True, exist_ok=True)
        destination = skills_dir / skill_name
        if destination.exists():
            msg = f'A Skill named "{skill_name}" is already installed'
            raise FileExistsError(msg)

        with tempfile.TemporaryDirectory(prefix=".skill-", dir=skills_dir) as temporary_dir:
            staging = Path(temporary_dir) / skill_name
            staging.mkdir()
            for entry in entries:
                source_path = PurePosixPath(entry.filename)
                relative_parts = source_path.parts[1:] if wrapper else source_path.parts
                target = staging.joinpath(*relative_parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
            staging.rename(destination)

    skill_file = destination / "SKILL.md"
    return SkillRead(
        name=_read_frontmatter_value(skill_file, "name") or skill_name,
        description=_read_frontmatter_value(skill_file, "description"),
        updated_at=datetime.fromtimestamp(skill_file.stat().st_mtime, tz=timezone.utc),
    )


@router.get("/", response_model=list[SkillRead])
async def list_skills(
    *,
    current_user: CurrentActiveUser,
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
) -> list[SkillRead]:
    """List Skills installed in the Langflow configuration directory."""
    del current_user
    return await asyncio.to_thread(_list_skills, _skills_directory(settings_service))


@router.post("/", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
async def upload_skill(
    *,
    current_user: CurrentActiveUser,
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
    file: Annotated[UploadFile, File(description="A ZIP archive containing one Skill")],
) -> SkillRead:
    """Validate and install a Skill ZIP archive."""
    del current_user
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Only ZIP archives can be uploaded")
    if file.size is not None and file.size > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="The Skill ZIP archive must be 25 MB or smaller")

    contents = await file.read(MAX_ARCHIVE_BYTES + 1)
    if len(contents) > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="The Skill ZIP archive must be 25 MB or smaller")

    try:
        return await asyncio.to_thread(_install_skill, contents, filename, _skills_directory(settings_service))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
