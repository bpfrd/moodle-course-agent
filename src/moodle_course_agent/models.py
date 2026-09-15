"""Shared domain models. Snapshots and sync plans are the source of truth."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ModuleType(str, Enum):
    LABEL = "label"
    PAGE = "page"
    URL = "url"
    FORUM = "forum"
    ASSIGN = "assign"
    UNKNOWN = "unknown"


SUPPORTED_MODULE_TYPES = {
    ModuleType.LABEL,
    ModuleType.PAGE,
    ModuleType.URL,
    ModuleType.FORUM,
    ModuleType.ASSIGN,
}


class ModuleSnapshot(BaseModel):
    """Normalized view of one course module (Moodle or local)."""

    local_id: str
    modname: str
    name: str
    visible: int = 1
    visibleoncoursepage: int = 1
    cmid: int | None = None
    sectionnum: int | None = None
    section_name: str = ""
    position: int = 0
    fields: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""
    source: Literal["moodle", "workspace"] = "moodle"


class SectionSnapshot(BaseModel):
    local_id: str
    name: str
    summary: str = ""
    visible: int = 1
    sectionnum: int | None = None
    position: int = 0
    is_template_section: bool = False
    modules: list[ModuleSnapshot] = Field(default_factory=list)
    content_hash: str = ""
    source: Literal["moodle", "workspace"] = "moodle"


class CourseSnapshot(BaseModel):
    course_id: int
    title: str = ""
    source: Literal["moodle", "workspace"]
    fetched_at: datetime
    sections: list[SectionSnapshot] = Field(default_factory=list)
    template_section_name: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "course_id": self.course_id,
            "title": self.title,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
            "section_count": len(self.sections),
            "module_count": sum(len(s.modules) for s in self.sections),
            "template_sections": [s.name for s in self.sections if s.is_template_section],
            "sections": [
                {
                    "sectionnum": s.sectionnum,
                    "name": s.name,
                    "visible": s.visible,
                    "is_template_section": s.is_template_section,
                    "modules": [
                        {
                            "cmid": m.cmid,
                            "modname": m.modname,
                            "name": m.name,
                            "visible": m.visible,
                            "local_id": m.local_id,
                        }
                        for m in s.modules
                    ],
                }
                for s in self.sections
            ],
        }

    def module_by_cmid(self, cmid: int) -> ModuleSnapshot | None:
        for section in self.sections:
            for module in section.modules:
                if module.cmid == cmid:
                    return module
        return None

    def section_by_num(self, sectionnum: int) -> SectionSnapshot | None:
        for section in self.sections:
            if section.sectionnum == sectionnum:
                return section
        return None


class ChangeKind(str, Enum):
    CREATE_ON_MOODLE = "create_on_moodle"
    UPDATE_ON_MOODLE = "update_on_moodle"
    CREATE_LOCAL = "create_local"
    UPDATE_LOCAL = "update_local"
    CONFLICT = "conflict"
    MOODLE_ONLY = "moodle_only"
    LOCAL_ONLY = "local_only"


class SyncAction(BaseModel):
    id: str
    kind: ChangeKind
    entity: Literal["section", "module"]
    summary: str
    local_path: str | None = None
    moodle_id: int | None = None
    sectionnum: int | None = None
    modname: str | None = None
    name: str | None = None
    mutates_moodle: bool = False
    conflict_reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SyncPlan(BaseModel):
    direction: Literal["to_moodle", "to_local", "preview"]
    generated_at: datetime
    actions: list[SyncAction] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)

    @property
    def moodle_mutations(self) -> list[SyncAction]:
        return [a for a in self.actions if a.mutates_moodle]

    @property
    def conflicts(self) -> list[SyncAction]:
        return [a for a in self.actions if a.kind == ChangeKind.CONFLICT]


class SyncRecord(BaseModel):
    """Last-known hashes used for conflict detection. Not LLM memory."""

    updated_at: datetime
    items: dict[str, dict[str, str]] = Field(default_factory=dict)


class MemoryFact(BaseModel):
    key: str
    value: str
    updated_at: datetime


class ConversationMemory(BaseModel):
    facts: list[MemoryFact] = Field(default_factory=list)


class BootstrapSummary(BaseModel):
    course_id: int
    course_title: str
    moodle_sections: int
    moodle_modules: int
    workspace_files: int
    workspace_empty: bool
    exported_moodle_to_workspace: bool = False
    previous_session_id: str | None = None
    sync_preview_counts: dict[str, int] = Field(default_factory=dict)
    template_sections: list[str] = Field(default_factory=list)
    message: str = ""
