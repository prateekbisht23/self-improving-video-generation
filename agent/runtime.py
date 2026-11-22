"""Side effects the editing graph needs, behind a small interface.

The graph only *decides*; a Recorder persists versions/actions and renders. Tests and the CLI use
InMemoryRecorder; the worker uses the database-backed recorder in services/worker/editing.py.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from editing.context import EditContext
from editing.timeline.schema import Timeline


class Recorder(Protocol):
    def save_plan(self, plan: dict) -> None: ...
    def save_version(self, timeline: Timeline, version: int, created_by: str) -> None: ...
    def record_action(self, **fields: Any) -> None: ...
    def render(self, timeline: Timeline, version: int) -> dict: ...


@dataclass
class InMemoryRecorder:
    out_dir: Path
    do_render: bool = True
    plan: dict | None = None
    versions: dict[int, Timeline] = field(default_factory=dict)
    actions: list[dict] = field(default_factory=list)
    renders: list[dict] = field(default_factory=list)

    def save_plan(self, plan):
        self.plan = plan

    def save_version(self, timeline, version, created_by):
        self.versions[version] = timeline

    def record_action(self, **fields):
        self.actions.append(fields)

    def render(self, timeline, version):
        if not self.do_render:
            return {"skipped": True, "version": version}
        from rendering.ffmpeg.render import render

        r = render(timeline, Path(self.out_dir) / f"v{version:03d}").to_dict()
        self.renders.append(r)
        return r


@dataclass
class EditDeps:
    """Passed to the graph through config['configurable']['deps'] (not stored in state)."""
    ctx: EditContext
    recorder: Recorder
    style: dict | None = None        # StyleProfileData.model_dump() of the reference, if any
    memory: list[str] = field(default_factory=list)  # creator preferences (Phase 4)
