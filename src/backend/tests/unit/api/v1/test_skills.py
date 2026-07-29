import io
import zipfile
from pathlib import Path

import pytest
from langflow.api.v1.skills import _install_skill


def make_skill_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    return buffer.getvalue()


def test_install_skill_from_wrapped_archive(tmp_path: Path):
    contents = make_skill_zip(
        {
            "example-skill/SKILL.md": "---\nname: Example Skill\ndescription: Does useful work\n---\n",
            "example-skill/scripts/run.py": "print('ok')\n",
        }
    )

    skill = _install_skill(contents, "upload.zip", tmp_path)

    assert skill.name == "Example Skill"
    assert skill.description == "Does useful work"
    assert (tmp_path / "example-skill" / "SKILL.md").is_file()
    assert (tmp_path / "example-skill" / "scripts" / "run.py").is_file()


def test_install_skill_from_flat_archive_uses_archive_name(tmp_path: Path):
    contents = make_skill_zip({"SKILL.md": "---\nname: Flat Skill\n---\n", "reference.md": "Reference"})

    _install_skill(contents, "flat-skill.zip", tmp_path)

    assert (tmp_path / "flat-skill" / "SKILL.md").is_file()


def test_install_skill_rejects_path_traversal(tmp_path: Path):
    contents = make_skill_zip({"SKILL.md": "---\nname: Unsafe\n---\n", "../outside.txt": "unsafe"})

    with pytest.raises(ValueError, match="Unsafe path"):
        _install_skill(contents, "unsafe.zip", tmp_path)

    assert not (tmp_path.parent / "outside.txt").exists()


def test_install_skill_rejects_windows_path_traversal(tmp_path: Path):
    contents = make_skill_zip({"SKILL.md": "---\nname: Unsafe\n---\n", "..\\outside.txt": "unsafe"})

    with pytest.raises(ValueError, match="Unsafe path"):
        _install_skill(contents, "unsafe.zip", tmp_path)


def test_install_skill_requires_root_skill_file(tmp_path: Path):
    contents = make_skill_zip({"nested/docs/readme.md": "Missing manifest"})

    with pytest.raises(ValueError, match=r"SKILL\.md"):
        _install_skill(contents, "missing.zip", tmp_path)


def test_install_skill_does_not_overwrite_existing_skill(tmp_path: Path):
    contents = make_skill_zip({"sample/SKILL.md": "---\nname: Sample\n---\n"})
    _install_skill(contents, "sample.zip", tmp_path)

    with pytest.raises(FileExistsError, match="already installed"):
        _install_skill(contents, "sample.zip", tmp_path)
