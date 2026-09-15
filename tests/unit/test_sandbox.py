from pathlib import Path

import pytest

from moodle_course_agent.workspace.sandbox import WorkspaceError, WorkspaceSandbox


def test_write_and_read(tmp_path: Path):
    box = WorkspaceSandbox(tmp_path)
    box.write_text("notes/hello.md", "# Hi\n")
    assert box.read_text("notes/hello.md") == "# Hi\n"
    assert "notes/hello.md" in box.list_files()


def test_rejects_parent_escape(tmp_path: Path):
    box = WorkspaceSandbox(tmp_path)
    with pytest.raises(WorkspaceError):
        box.resolve("../secret.txt")


def test_absolute_path_is_contained(tmp_path: Path):
    box = WorkspaceSandbox(tmp_path)
    box.write_text("etc/passwd", "not-system")
    assert box.read_text("/etc/passwd") == "not-system"



def test_delete_nonempty_dir(tmp_path: Path):
    box = WorkspaceSandbox(tmp_path)
    box.write_text("a/b.txt", "x")
    with pytest.raises(WorkspaceError):
        box.delete("a")


def test_rename(tmp_path: Path):
    box = WorkspaceSandbox(tmp_path)
    box.write_text("old.md", "v")
    box.rename("old.md", "new.md")
    assert box.read_text("new.md") == "v"
