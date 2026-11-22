"""Failure collection (FR-11): failed checks of one agent version on the DEVELOPMENT split only.

The improvement loop diagnoses on development tasks, selects on validation (experiments) and never
sees holdout. This module is the data-access boundary: asking for any other split raises.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select

from benchmarks.schemas.task import HoldoutAccessError, load_tasks
from db.models import EditingSession, Evaluation, SessionStatus

DIAGNOSIS_SPLITS = ("development",)


@dataclass
class FailureRecord:
    issue_id: int | None          # evaluation_issues.id (None for a session that produced no render)
    session_id: str
    evaluation_id: str | None
    task: str
    check_id: str
    category: str
    kind: str
    severity: str
    message: str
    explanation: str = ""
    evidence: list = field(default_factory=list)
    trace_id: str | None = None


@dataclass
class FailureSet:
    agent_version: str
    sessions: int                  # sessions analysed (rendered or not)
    renders: int                   # evaluated renders
    evaluated_checks: Counter      # check_id -> how many renders produced a verdict for it
    records: list[FailureRecord]


def _norm_error(msg: str) -> str:
    if re.search(r"duration [\d.]+s outside target", msg or ""):
        return "duration outside target"
    return re.sub(r"[\d.]+", "#", (msg or "agent did not finish"))[:120]


def collect(s, agent_version: str, splits: tuple[str, ...] = DIAGNOSIS_SPLITS) -> FailureSet:
    bad = set(splits) - set(DIAGNOSIS_SPLITS)
    if bad:
        raise HoldoutAccessError(f"failure diagnosis may only read {DIAGNOSIS_SPLITS}, not {sorted(bad)}")
    task_ids = {t.id for t in load_tasks(list(splits))}
    sessions = [e for e in s.scalars(select(EditingSession).where(EditingSession.agent_version == agent_version))
                if (e.constraints or {}).get("benchmark_task") in task_ids]
    # a task may have been run more than once with this version (e.g. a resumed run): keep the latest
    latest: dict[str, EditingSession] = {}
    for e in sorted(sessions, key=lambda e: e.created_at):
        if e.status in (SessionStatus.rendered, SessionStatus.failed):
            latest[e.constraints["benchmark_task"]] = e
    records: list[FailureRecord] = []
    evaluated: Counter = Counter()
    renders = 0
    for task, e in sorted(latest.items()):
        if e.status == SessionStatus.failed:
            records.append(FailureRecord(None, str(e.id), None, task, "agent.no_render", "agent", "deterministic",
                                         "critical", _norm_error(e.error or ""), explanation=(e.error or "")[:500],
                                         trace_id=e.trace_id))
            continue
        ev = s.scalar(select(Evaluation).where(Evaluation.session_id == e.id)
                      .order_by(Evaluation.created_at.desc()))
        if ev is None:
            continue
        renders += 1
        for c in ev.report["checks"]:
            if c["passed"] is not None:
                evaluated[c["id"]] += 1
        for i in ev.issues:
            records.append(FailureRecord(i.id, str(e.id), str(ev.id), task, i.check_id, i.category, i.kind,
                                         i.severity, i.message, i.explanation or "", list(i.evidence or []),
                                         e.trace_id))
    return FailureSet(agent_version, len(latest), renders, evaluated, records)
