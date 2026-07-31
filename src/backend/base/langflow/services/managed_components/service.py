from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from lfx.extension.bundle_registry import get_default_registry
from lfx.extension.loader import load_inline_bundle
from lfx.interface.components import component_cache, get_and_cache_all_types_dict

if TYPE_CHECKING:
    from lfx.services.settings.service import SettingsService

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1000
MAX_SOURCE_BYTES = 500 * 1024
BUNDLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

_refresh_lock = asyncio.Lock()


def managed_components_root(settings_service: SettingsService) -> Path:
    config_dir = settings_service.settings.config_dir
    if not config_dir:
        raise HTTPException(status_code=500, detail="Langflow config directory is not configured")
    return Path(config_dir) / "managed_components"


def active_components_root(settings_service: SettingsService) -> Path:
    return managed_components_root(settings_service) / "active"


def disabled_components_root(settings_service: SettingsService) -> Path:
    return managed_components_root(settings_service) / "disabled"


def ensure_managed_components_path(settings_service: SettingsService) -> Path:
    active_root = active_components_root(settings_service)
    active_root.mkdir(parents=True, exist_ok=True)
    path = str(active_root)
    if path not in settings_service.settings.components_path:
        settings_service.settings.components_path.append(path)
    return active_root


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
            msg = f"Symbolic links are not allowed in component archives: {entry.filename}"
            raise ValueError(msg)
        total_size += entry.file_size
        if total_size > MAX_EXTRACTED_BYTES:
            msg = "The extracted component bundle is larger than 100 MB"
            raise ValueError(msg)
        roots.add(path.parts[0])

    wrapper = (
        next(iter(roots))
        if len(roots) == 1 and all(len(PurePosixPath(entry.filename).parts) > 1 for entry in entries)
        else None
    )
    return entries, wrapper


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    return str(value)


def _field_metadata(field: Any) -> dict[str, Any]:
    raw = _json_safe(field)
    if isinstance(raw, dict):
        return raw
    return {"name": getattr(field, "name", ""), "value": raw}


def _component_metadata(loaded: Any) -> dict[str, Any]:
    instance = loaded.klass()
    return {
        "namespaced_id": loaded.namespaced_id,
        "class_name": loaded.class_name,
        "display_name": getattr(instance, "display_name", loaded.class_name),
        "description": getattr(instance, "description", "") or "",
        "documentation": getattr(instance, "documentation", None),
        "icon": getattr(instance, "icon", None),
        "inputs": [_field_metadata(field) for field in getattr(instance, "inputs", [])],
        "outputs": [_field_metadata(field) for field in getattr(instance, "outputs", [])],
    }


def _bundle_description(bundle_root: Path) -> str | None:
    bundle_file = bundle_root / "bundle.json"
    if not bundle_file.is_file():
        return None
    try:
        payload = json.loads(bundle_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(payload, dict) and isinstance(payload.get("description"), str):
        return payload["description"].strip() or None
    return None


def install_component_bundle(contents: bytes, archive_name: str, settings_service: SettingsService) -> dict[str, Any]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        msg = "The uploaded file is not a valid ZIP archive"
        raise ValueError(msg) from exc

    active_root = ensure_managed_components_path(settings_service)
    with archive:
        entries, wrapper = _validated_entries(archive)
        bundle_name = wrapper or Path(archive_name).stem
        if not BUNDLE_NAME_RE.fullmatch(bundle_name):
            msg = "The bundle directory or ZIP name must use lowercase letters, numbers, and underscores"
            raise ValueError(msg)
        destination = active_root / bundle_name
        disabled_destination = disabled_components_root(settings_service) / bundle_name
        if destination.exists() or disabled_destination.exists():
            msg = f'A component bundle named "{bundle_name}" is already installed'
            raise FileExistsError(msg)

        active_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".component-", dir=active_root) as temporary_dir:
            staging = Path(temporary_dir) / bundle_name
            staging.mkdir()
            for entry in entries:
                source_path = PurePosixPath(entry.filename)
                relative_parts = source_path.parts[1:] if wrapper else source_path.parts
                target = staging.joinpath(*relative_parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

            result = load_inline_bundle(staging)
            if not result.components:
                errors = "; ".join(error.message for error in result.errors)
                raise ValueError(errors or "No valid Langflow components were found in the bundle")
            metadata = [_component_metadata(component) for component in result.components]
            description = _bundle_description(staging)
            staging.rename(destination)

    return {
        "bundle_name": bundle_name,
        "extension_id": result.extension_id or bundle_name,
        "version": result.extension_version or "0.0.0",
        "description": description,
        "components": metadata,
        "source_hash": hashlib.sha256(contents).hexdigest(),
        "archive_path": str(destination),
    }


async def refresh_managed_components(settings_service: SettingsService, *, removed_bundle: str | None = None) -> None:
    async with _refresh_lock:
        ensure_managed_components_path(settings_service)
        if removed_bundle:
            get_default_registry().remove_bundle(removed_bundle)
        component_cache.all_types_dict = None
        component_cache.type_to_current_hash = None
        component_cache.all_known_hashes = None
        component_cache.code_by_hash = None
        component_cache.fully_loaded_components.clear()
        await get_and_cache_all_types_dict(settings_service)


def disable_component_bundle(bundle_name: str, settings_service: SettingsService) -> Path:
    source = active_components_root(settings_service) / bundle_name
    if not source.is_dir():
        msg = f'Component bundle "{bundle_name}" is not installed'
        raise FileNotFoundError(msg)
    destination_root = disabled_components_root(settings_service)
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / bundle_name
    if destination.exists():
        msg = f'Component bundle "{bundle_name}" is already disabled'
        raise FileExistsError(msg)
    source.rename(destination)
    return destination


def read_bundle_source(bundle_path: str) -> str:
    root = Path(bundle_path)
    if not root.is_dir():
        return ""
    chunks: list[str] = []
    total = 0
    for source_file in sorted(root.rglob("*.py")):
        try:
            content = source_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = source_file.relative_to(root).as_posix()
        chunk = f"# {relative}\n{content}"
        total += len(chunk.encode())
        if total > MAX_SOURCE_BYTES:
            chunks.append("# Source truncated at 500 KB")
            break
        chunks.append(chunk)
    return "\n\n".join(chunks)
