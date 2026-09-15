"""JSON file persistence for snapshots, sync records, memory, and sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from moodle_course_agent.models import (
    ConversationMemory,
    CourseSnapshot,
    MemoryFact,
    SyncPlan,
    SyncRecord,
    utcnow,
)


class StateStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.snapshots_dir = self.data_dir / "snapshots"
        self.sessions_dir = self.data_dir / "sessions"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _write(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(payload, "model_dump"):
            data = payload.model_dump(mode="json")
        else:
            data = payload
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def _read(self, path: Path) -> Any:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_moodle_snapshot(self, snapshot: CourseSnapshot) -> Path:
        path = self.snapshots_dir / "moodle.json"
        self._write(path, snapshot)
        return path

    def save_workspace_snapshot(self, snapshot: CourseSnapshot) -> Path:
        path = self.snapshots_dir / "workspace.json"
        self._write(path, snapshot)
        return path

    def load_moodle_snapshot(self) -> CourseSnapshot | None:
        data = self._read(self.snapshots_dir / "moodle.json")
        return CourseSnapshot.model_validate(data) if data else None

    def load_workspace_snapshot(self) -> CourseSnapshot | None:
        data = self._read(self.snapshots_dir / "workspace.json")
        return CourseSnapshot.model_validate(data) if data else None

    def save_sync_record(self, record: SyncRecord) -> None:
        self._write(self.data_dir / "sync_record.json", record)

    def load_sync_record(self) -> SyncRecord:
        data = self._read(self.data_dir / "sync_record.json")
        if not data:
            return SyncRecord(updated_at=utcnow(), items={})
        return SyncRecord.model_validate(data)

    def save_sync_plan(self, plan: SyncPlan) -> None:
        self._write(self.data_dir / "last_sync_plan.json", plan)

    def load_sync_plan(self) -> SyncPlan | None:
        data = self._read(self.data_dir / "last_sync_plan.json")
        return SyncPlan.model_validate(data) if data else None

    def load_memory(self) -> ConversationMemory:
        data = self._read(self.data_dir / "memory.json")
        if not data:
            return ConversationMemory()
        return ConversationMemory.model_validate(data)

    def save_memory(self, memory: ConversationMemory) -> None:
        self._write(self.data_dir / "memory.json", memory)

    def remember(self, key: str, value: str) -> ConversationMemory:
        memory = self.load_memory()
        remaining = [f for f in memory.facts if f.key != key]
        remaining.append(MemoryFact(key=key, value=value, updated_at=utcnow()))
        memory.facts = remaining[-50:]
        self.save_memory(memory)
        return memory

    def last_session_id(self) -> str | None:
        pointer = self.data_dir / "last_session.txt"
        if pointer.exists():
            return pointer.read_text(encoding="utf-8").strip() or None
        return None

    def set_last_session_id(self, session_id: str) -> None:
        (self.data_dir / "last_session.txt").write_text(session_id, encoding="utf-8")

    def list_sessions(self) -> list[str]:
        if not self.sessions_dir.exists():
            return []
        ids = {p.name for p in self.sessions_dir.iterdir() if p.is_dir()}
        return sorted(ids)
