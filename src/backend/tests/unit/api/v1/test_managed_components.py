import io
import zipfile
from types import SimpleNamespace

import langflow.api.v1.managed_components as managed_components_api
import pytest
from fastapi import status
from httpx import AsyncClient
from langflow.services.managed_components.service import _validated_entries


def _zip_bytes(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_component_archive_rejects_path_traversal() -> None:
    with (
        zipfile.ZipFile(io.BytesIO(_zip_bytes({"../escape.py": "pass"}))) as archive,
        pytest.raises(ValueError, match="Unsafe path"),
    ):
        _validated_entries(archive)


async def test_managed_components_require_superuser(
    client: AsyncClient,
    logged_in_headers,
) -> None:
    response = await client.get("api/v1/managed-components", headers=logged_in_headers)

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_admin_can_upload_list_and_view_component(
    client: AsyncClient,
    logged_in_headers_super_user,
    monkeypatch,
    tmp_path,
) -> None:
    bundle_path = tmp_path / "demo_bundle"
    bundle_path.mkdir()
    (bundle_path / "demo.py").write_text("class DemoComponent: pass\n", encoding="utf-8")

    def fake_install(_contents, _filename, _settings):
        return {
            "bundle_name": "demo_bundle",
            "extension_id": "demo-bundle",
            "version": "1.0.0",
            "description": "Demo bundle",
            "components": [
                {
                    "namespaced_id": "ext:demo_bundle:DemoComponent@extra",
                    "class_name": "DemoComponent",
                    "display_name": "Demo",
                    "description": "Demo component",
                    "documentation": None,
                    "icon": None,
                    "inputs": [],
                    "outputs": [],
                }
            ],
            "source_hash": "0" * 64,
            "archive_path": str(bundle_path),
        }

    def fake_disable(_bundle_name, _settings):
        disabled_path = tmp_path / "disabled" / "demo_bundle"
        disabled_path.mkdir(parents=True)
        return disabled_path

    async def fake_refresh(_settings, *, removed_bundle=None):
        del removed_bundle

    async def fake_get_types(*, settings_service):
        del settings_service
        return {
            "inputs": {
                "ChatInput": {
                    "display_name": "Chat Input",
                    "description": "Built-in chat input",
                    "template": {},
                    "outputs": [],
                }
            }
        }

    def fake_translate(all_types, locale):
        assert locale == "zh-Hans"
        translated = all_types.copy()
        translated["inputs"] = {
            **all_types["inputs"],
            "ChatInput": {
                **all_types["inputs"]["ChatInput"],
                "display_name": "聊天输入",
                "description": "系统内置聊天输入",
            },
        }
        return translated

    monkeypatch.setattr(managed_components_api, "install_component_bundle", fake_install)
    monkeypatch.setattr(managed_components_api, "disable_component_bundle", fake_disable)
    monkeypatch.setattr(managed_components_api, "refresh_managed_components", fake_refresh)
    monkeypatch.setattr(managed_components_api, "get_and_cache_all_types_dict", fake_get_types)
    monkeypatch.setattr(managed_components_api, "translate_component_dict", fake_translate)
    monkeypatch.setattr(
        managed_components_api,
        "get_settings_service",
        lambda: SimpleNamespace(settings=SimpleNamespace(allow_custom_components=True)),
    )

    upload = await client.post(
        "api/v1/managed-components",
        headers=logged_in_headers_super_user,
        files={"file": ("demo_bundle.zip", _zip_bytes({"demo_bundle/demo.py": "pass"}), "application/zip")},
    )
    assert upload.status_code == status.HTTP_201_CREATED
    created = upload.json()
    assert created["bundle_name"] == "demo_bundle"
    assert created["status"] == "ACTIVE"

    zh_headers = {**logged_in_headers_super_user, "Accept-Language": "zh-Hans"}
    listed = await client.get("api/v1/managed-components", headers=zh_headers)
    assert listed.status_code == status.HTTP_200_OK
    assert any(item["id"] == created["id"] for item in listed.json())
    system_group = next(item for item in listed.json() if item["id"] == "system:inputs")
    assert system_group["origin"] == "SYSTEM"
    assert system_group["can_disable"] is False
    assert system_group["components"][0]["display_name"] == "聊天输入"
    assert system_group["components"][0]["description"] == "系统内置聊天输入"

    detail = await client.get(
        f"api/v1/managed-components/{created['id']}",
        headers=logged_in_headers_super_user,
    )
    assert detail.status_code == status.HTTP_200_OK
    assert "DemoComponent" in detail.json()["source_code"]
    assert detail.json()["usage_count"] == 0

    disabled = await client.post(
        f"api/v1/managed-components/{created['id']}/disable",
        headers=logged_in_headers_super_user,
    )
    assert disabled.status_code == status.HTTP_200_OK
    assert disabled.json()["status"] == "DISABLED"
