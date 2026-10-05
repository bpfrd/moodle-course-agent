"""Shared application: Moodle client, workspace, snapshots, and sync."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from moodle_course_agent.config import Settings
from moodle_course_agent.models import BootstrapSummary, ChangeKind, CourseSnapshot, SyncPlan, SyncRecord
from moodle_course_agent.moodle.client import MoodleClient
from moodle_course_agent.moodle.fakes import FakeMoodleClient
from moodle_course_agent.moodle.snapshot import build_moodle_snapshot
from moodle_course_agent.state import StateStore
from moodle_course_agent.sync import (
    action_record_keys,
    apply_to_local,
    apply_to_moodle,
    build_sync_plan,
    record_from_snapshots,
)
from moodle_course_agent.workspace import build_workspace_snapshot, export_snapshot_to_workspace
from moodle_course_agent.workspace.sandbox import WorkspaceSandbox


def seed_demo_client() -> FakeMoodleClient:
    client = FakeMoodleClient(courseid=42)
    client._sections = []
    client._next_section_id = 1
    client._next_cmid = 100
    client.create_section("General", "<p>Course intro</p>", position=1)
    client.create_section("Week 1", "<p>Getting started</p>", position=2)
    client.create_section("Modulentwicklung [RK only]", "<p>Templates</p>", position=3, visible=0)
    client.create_label(0, "<p>Welcome to the course.</p>", name="Welcome")
    client.create_page(
        1,
        "Syllabus",
        "<p>Overview</p>",
        "<h3>Syllabus</h3><p>Week-by-week plan.</p>",
    )
    client.create_assign(
        1,
        "Homework 1",
        "<p>First assignment</p>",
        "<p>Submit a short reflection.</p>",
        duedate=0,
        zeitaufwand="1h",
    )
    client.create_assign(
        2,
        "Vorlage: Aufgabe ohne Abgabe",
        "<p>Template intro</p>",
        "<p>Template body</p>",
        visible=0,
    )
    client.create_assign(
        2,
        "Vorlage: Aufgabe mit Abgabe",
        "<p>Template intro with submission</p>",
        "<p>Template body with submission</p>",
        visible=0,
    )
    client.create_forum(1, "Peer forum", "<p>Discuss here.</p>")
    return client


class CourseApplication:
    """Owns Moodle client, workspace, snapshots, and sync. UI-agnostic."""

    def __init__(
        self,
        settings: Settings,
        moodle: MoodleClient | FakeMoodleClient | None = None,
    ) -> None:
        self.settings = settings
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = WorkspaceSandbox(settings.workspace_dir)
        self.store = StateStore(settings.data_dir)
        self.moodle = moodle or self._connect_moodle()
        self.moodle_snapshot: CourseSnapshot | None = None
        self.workspace_snapshot: CourseSnapshot | None = None

    def _connect_moodle(self) -> MoodleClient | FakeMoodleClient:
        if self.settings.moodle_mock:
            return seed_demo_client()
        self.settings.require_moodle()
        return MoodleClient(
            base_url=self.settings.base_url,
            token=self.settings.wstoken,
            courseid=self.settings.course_id,
            timeout=self.settings.moodle_timeout,
        )

    def refresh_moodle_snapshot(self, *, fetch_bodies: bool = True) -> CourseSnapshot:
        snapshot = build_moodle_snapshot(
            self.moodle,
            template_section_name=self.settings.template_section_name,
            fetch_bodies=fetch_bodies,
        )
        self.moodle_snapshot = snapshot
        self.store.save_moodle_snapshot(snapshot)
        return snapshot

    def refresh_workspace_snapshot(self) -> CourseSnapshot:
        snapshot = build_workspace_snapshot(
            self.workspace,
            course_id=int(getattr(self.moodle, "courseid", self.settings.course_id) or 0),
            template_section_name=self.settings.template_section_name,
        )
        self.workspace_snapshot = snapshot
        self.store.save_workspace_snapshot(snapshot)
        return snapshot

    def bootstrap(self) -> BootstrapSummary:
        moodle = self.refresh_moodle_snapshot()
        exported = False
        if self.workspace.is_empty() or not self.workspace.exists("course.yaml"):
            export_snapshot_to_workspace(self.workspace, moodle, overwrite=True)
            exported = True
        workspace = self.refresh_workspace_snapshot()
        record = self.store.load_sync_record()
        plan = build_sync_plan(moodle, workspace, record, direction="preview")
        self.store.save_sync_plan(plan)
        if not record.items:
            self.store.save_sync_record(record_from_snapshots(moodle, workspace))
        return BootstrapSummary(
            course_id=moodle.course_id,
            course_title=moodle.title,
            moodle_sections=len(moodle.sections),
            moodle_modules=sum(len(s.modules) for s in moodle.sections),
            workspace_files=len(self.workspace.list_files()),
            workspace_empty=False,
            exported_moodle_to_workspace=exported,
            previous_session_id=self.store.last_session_id(),
            sync_preview_counts=plan.counts,
            template_sections=[s.name for s in moodle.sections if s.is_template_section],
            message=self._bootstrap_message(moodle, exported, plan),
        )

    def _bootstrap_message(self, moodle: CourseSnapshot, exported: bool, plan: SyncPlan) -> str:
        parts = [
            f"Loaded Moodle course {moodle.course_id} "
            f"({len(moodle.sections)} sections, "
            f"{sum(len(s.modules) for s in moodle.sections)} modules)."
        ]
        if exported:
            parts.append("Workspace was empty, so a local Markdown/YAML copy was created.")
        if plan.counts.get("total"):
            parts.append(f"Sync preview: {plan.counts}.")
        else:
            parts.append("Local workspace matches the Moodle snapshot.")
        return " ".join(parts)

    def status(self) -> dict[str, Any]:
        moodle = self.moodle_snapshot or self.refresh_moodle_snapshot()
        workspace = self.workspace_snapshot or self.refresh_workspace_snapshot()
        plan = build_sync_plan(moodle, workspace, self.store.load_sync_record(), direction="preview")
        return {
            "course_id": moodle.course_id,
            "moodle": moodle.summary(),
            "workspace_tree": self.workspace.tree(),
            "workspace_files": self.workspace.list_files(),
            "sync": plan.model_dump(mode="json"),
            "memory": self.store.load_memory().model_dump(mode="json"),
            "sessions": self.store.list_sessions(),
            "mock": self.settings.moodle_mock,
        }

    def preview_sync(self, direction: str = "preview") -> SyncPlan:
        moodle = self.refresh_moodle_snapshot()
        workspace = self.refresh_workspace_snapshot()
        plan = build_sync_plan(
            moodle, workspace, self.store.load_sync_record(), direction=direction
        )
        self.store.save_sync_plan(plan)
        return plan

    def apply_sync(
        self,
        direction: str,
        *,
        approved: bool,
        skip_conflicts: bool = True,
    ) -> dict[str, Any]:
        plan = self.preview_sync(direction)
        if direction == "to_moodle":
            if not approved:
                return {
                    "ok": False,
                    "error": "Moodle sync was not approved.",
                    "plan": plan.model_dump(mode="json"),
                }
            to_apply = plan
            if skip_conflicts:
                to_apply = plan.model_copy(
                    update={"actions": [a for a in plan.actions if a.kind.value != "conflict"]}
                )
            results = apply_to_moodle(
                self.moodle,
                self.workspace,
                to_apply,
                template_section_name=self.settings.template_section_name,
            )
            applied = {item["id"] for item in results if item.get("ok") is True}
            pushed = {
                key for a in to_apply.actions if a.id in applied for key in action_record_keys(a)
            }
            written = self.sync_workspace_from_moodle(synced=pushed)
            failed = [item for item in results if item.get("ok") is False]
            return {
                "ok": not failed,
                "results": results,
                "plan": to_apply.model_dump(mode="json"),
                "workspace_updated": written,
            }

        if direction == "to_local":
            previous = self.store.load_sync_record()
            moodle = self.moodle_snapshot or self.refresh_moodle_snapshot()
            written = apply_to_local(self.workspace, moodle, plan)
            workspace = self.refresh_workspace_snapshot()
            pulled = {
                key
                for a in plan.actions
                if a.kind != ChangeKind.CONFLICT
                for key in action_record_keys(a)
            }
            self.store.save_sync_record(
                record_from_snapshots(moodle, workspace, previous, synced=pulled)
            )
            return {"ok": True, "written": written, "plan": plan.model_dump(mode="json")}

        return {"ok": False, "error": f"Unknown direction {direction}"}

    def sync_workspace_from_moodle(self, *, synced: set[str] = frozenset()) -> list[str]:
        """Pull Moodle-side changes into local files without discarding local work.

        Pulls modules/sections that are new on Moodle, changed only on Moodle, or
        were just pushed (``synced`` record keys), so Moodle's normalized form
        lands locally. Unpushed local edits, conflicts, and pairs with no sync
        baseline are left alone and keep their previous baseline.
        """
        moodle = self.refresh_moodle_snapshot()
        workspace = self.refresh_workspace_snapshot()
        previous = self.store.load_sync_record()
        # Dropping the baseline of just-pushed pairs makes them pullable below.
        basis = SyncRecord(
            updated_at=previous.updated_at,
            items={k: v for k, v in previous.items.items() if k not in synced},
        )
        plan = build_sync_plan(moodle, workspace, basis, direction="to_local")
        pull = [
            a
            for a in plan.actions
            if a.kind == ChangeKind.CREATE_LOCAL
            or (
                a.kind == ChangeKind.UPDATE_LOCAL
                and (a.details.get("changed_side") == "moodle" or action_record_keys(a) & synced)
            )
        ]
        written = apply_to_local(self.workspace, moodle, plan.model_copy(update={"actions": pull}))
        workspace = self.refresh_workspace_snapshot()
        pulled = set(synced).union(*(action_record_keys(a) for a in pull))
        self.store.save_sync_record(
            record_from_snapshots(moodle, workspace, previous, synced=pulled)
        )
        return written

    def after_moodle_write(self) -> list[str]:
        """Keep the workspace aligned after a remote Moodle change."""
        return self.sync_workspace_from_moodle()

    def new_session_id(self) -> str:
        session_id = uuid4().hex[:10]
        self.store.set_last_session_id(session_id)
        (self.settings.sessions_dir / session_id).mkdir(parents=True, exist_ok=True)
        return session_id
