"""Path-restricted filesystem access for the teacher workspace."""

from __future__ import annotations

import os
from pathlib import Path

TEXT_EXTENSIONS = {".md", ".yaml", ".yml", ".txt", ".json", ".html"}
MAX_FILE_BYTES = 2_000_000


class WorkspaceError(ValueError):
    pass


class WorkspaceSandbox:
    """All paths are resolved under ``root``; escapes raise WorkspaceError."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str | Path) -> Path:
        rel = str(relative).replace("\\", "/").lstrip("/")
        if rel in {"", "."}:
            return self.root
        if ".." in Path(rel).parts:
            raise WorkspaceError("Path may not contain '..'")
        candidate = (self.root / rel).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError(f"Path escapes workspace: {relative}") from exc
        return candidate

    def relative_to_root(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.root)).replace("\\", "/")

    def list_dir(self, relative: str = ".") -> list[dict[str, str | int | bool]]:
        directory = self.resolve(relative)
        if not directory.exists():
            raise WorkspaceError(f"Directory not found: {relative}")
        if not directory.is_dir():
            raise WorkspaceError(f"Not a directory: {relative}")
        entries: list[dict[str, str | int | bool]] = []
        for child in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith(".") and child.name not in {".", ".."}:
                continue
            entries.append(
                {
                    "name": child.name,
                    "path": self.relative_to_root(child),
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else 0,
                }
            )
        return entries

    def tree(self, max_depth: int = 6) -> list[str]:
        lines: list[str] = []
        root = self.root

        def walk(current: Path, prefix: str, depth: int) -> None:
            if depth > max_depth:
                return
            children = [
                c
                for c in sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                if not c.name.startswith(".")
            ]
            for index, child in enumerate(children):
                last = index == len(children) - 1
                branch = "└── " if last else "├── "
                lines.append(f"{prefix}{branch}{child.name}{'/' if child.is_dir() else ''}")
                if child.is_dir():
                    extension = "    " if last else "│   "
                    walk(child, prefix + extension, depth + 1)

        lines.append(f"{root.name}/")
        walk(root, "", 1)
        return lines

    def read_text(self, relative: str) -> str:
        path = self.resolve(relative)
        if not path.is_file():
            raise WorkspaceError(f"File not found: {relative}")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise WorkspaceError(f"File too large: {relative}")
        return path.read_text(encoding="utf-8")

    def write_text(self, relative: str, content: str, *, overwrite: bool = True) -> str:
        path = self.resolve(relative)
        if path.exists() and path.is_dir():
            raise WorkspaceError(f"Refusing to overwrite directory: {relative}")
        if path.exists() and not overwrite:
            raise WorkspaceError(f"File already exists: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return self.relative_to_root(path)

    def create_dir(self, relative: str) -> str:
        path = self.resolve(relative)
        path.mkdir(parents=True, exist_ok=True)
        return self.relative_to_root(path)

    def rename(self, source: str, dest: str) -> str:
        src = self.resolve(source)
        dst = self.resolve(dest)
        if not src.exists():
            raise WorkspaceError(f"Source not found: {source}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.rename(src, dst)
        return self.relative_to_root(dst)

    def delete(self, relative: str) -> str:
        path = self.resolve(relative)
        if not path.exists():
            raise WorkspaceError(f"Not found: {relative}")
        if path.is_dir():
            try:
                path.rmdir()
            except OSError as exc:
                raise WorkspaceError(f"Directory is not empty: {relative}") from exc
        else:
            path.unlink()
        return relative

    def exists(self, relative: str) -> bool:
        try:
            return self.resolve(relative).exists()
        except WorkspaceError:
            return False

    def is_empty(self) -> bool:
        if not self.root.exists():
            return True
        for child in self.root.iterdir():
            if child.name.startswith("."):
                continue
            return False
        return True

    def list_files(self, suffixes: set[str] | None = None) -> list[str]:
        suffixes = suffixes or TEXT_EXTENSIONS
        files: list[str] = []
        for path in self.root.rglob("*"):
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(self.root).parts):
                if path.suffix.lower() in suffixes:
                    files.append(self.relative_to_root(path))
        return sorted(files)
