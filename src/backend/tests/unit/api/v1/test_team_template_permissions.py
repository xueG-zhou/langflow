from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langflow.api.v1.team_templates import _ensure_template_delete, _get_visible_template
from langflow.services.database.models.team_template import TeamTemplate, TeamTemplateVisibility


def _template(owner_id, visibility=TeamTemplateVisibility.PRIVATE.value):
    return TeamTemplate(
        name="Template",
        flow_data={"nodes": [], "edges": []},
        created_by=owner_id,
        visibility=visibility,
    )


def test_named_manager_cannot_delete_another_users_private_template() -> None:
    row = _template(uuid4())
    user = SimpleNamespace(id=uuid4(), username="langflow", is_superuser=False)

    with pytest.raises(HTTPException) as exc_info:
        _ensure_template_delete(row, user)

    assert exc_info.value.status_code == 403


def test_regular_user_cannot_delete_another_users_template() -> None:
    row = _template(uuid4())
    user = SimpleNamespace(id=uuid4(), username="regular-user", is_superuser=False)

    with pytest.raises(HTTPException) as exc_info:
        _ensure_template_delete(row, user)

    assert exc_info.value.status_code == 403


def test_superuser_can_manage_public_template() -> None:
    row = _template(uuid4(), TeamTemplateVisibility.PUBLIC.value)
    user = SimpleNamespace(id=uuid4(), username="admin", is_superuser=True)

    _ensure_template_delete(row, user)


def test_superuser_cannot_manage_private_template() -> None:
    row = _template(uuid4())
    user = SimpleNamespace(id=uuid4(), username="admin", is_superuser=True)

    with pytest.raises(HTTPException) as exc_info:
        _ensure_template_delete(row, user)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_private_template_is_hidden_from_other_users() -> None:
    row = _template(uuid4())

    class Session:
        async def get(self, _model, _template_id):
            return row

    user = SimpleNamespace(id=uuid4(), username="regular-user", is_superuser=False)

    with pytest.raises(HTTPException) as exc_info:
        await _get_visible_template(Session(), row.id, user)

    assert exc_info.value.status_code == 404
