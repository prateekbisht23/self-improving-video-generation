"""Evaluate a stored render and persist the report (+ one issue row per failed check)."""

import uuid

from sqlalchemy import select

from config.settings import get_settings
from db.models import Evaluation, EvaluationIssue, Render, StyleProfile, TranscriptSegment
from db.session import session_scope
from evaluation.graph import evaluate
from evaluation.inputs import EvalInput
from evaluation.schemas import EvaluationReport


def build_eval_input(s, render: Render) -> EvalInput:
    v = render.timeline_version
    e = v.session
    c = e.constraints or {}
    words = {}
    for a in e.source_asset_ids:
        segs = s.scalars(select(TranscriptSegment).where(TranscriptSegment.asset_id == uuid.UUID(a))).all()
        words[a] = [(w["start"], w["end"], w["text"]) for g in segs for w in (g.words or [])]
    reference = None
    if e.reference_asset_id:
        sp = s.scalar(select(StyleProfile).where(StyleProfile.asset_id == e.reference_asset_id)
                      .order_by(StyleProfile.created_at.desc()))
        reference = sp.profile if sp else None
    tl = dict(v.timeline)
    tl["_hash"] = v.content_hash
    return EvalInput(render_path=render.path, instructions=e.instructions,
                     min_duration=c.get("min_duration", 15), max_duration=c.get("max_duration", 30),
                     aspect_ratio=c.get("aspect_ratio", "9:16"), captions_required=c.get("captions_required"),
                     must_include=c.get("must_include", []), must_exclude=c.get("must_exclude", []),
                     timeline=tl, source_words=words, reference=reference,
                     preferences=[m["statement"] for m in (e.memory_used or []) if "statement" in m])


def evaluate_render(render_id: uuid.UUID | str, *, judges_on: bool | None = None) -> dict:
    render_id = uuid.UUID(str(render_id))
    with session_scope() as s:
        r = s.get(Render, render_id)
        if r is None or not r.path:
            raise LookupError(f"render {render_id} not found or has no file")
        x = build_eval_input(s, r)
        version_id, session_id = r.timeline_version_id, r.timeline_version.session_id
    judges_on = get_settings().pipeline_vision if judges_on is None else judges_on
    run_id = uuid.uuid4()
    rep: EvaluationReport = evaluate(x, judges_on=judges_on, run_id=run_id,
                                     metadata={"render_id": str(render_id), "session_id": str(session_id)})
    with session_scope() as s:
        ev = Evaluation(render_id=render_id, timeline_version_id=version_id, session_id=session_id,
                        evaluator_version=rep.evaluator_version, judge_model=rep.judge_model,
                        technical_gate_passed=rep.technical_gate_passed, pass_rate=rep.pass_rate,
                        by_category=rep.by_category, report=rep.model_dump(), trace_id=str(run_id))
        for c in rep.checks:
            if c.passed is False:
                first = c.evidence[0] if c.evidence else None
                ev.issues.append(EvaluationIssue(
                    check_id=c.id, category=c.category, kind=c.kind, severity=c.severity, message=c.message,
                    explanation=c.explanation, evidence=[e.model_dump() for e in c.evidence],
                    start=first.start if first else None, end=first.end if first else None))
        s.add(ev)
        s.flush()
        return {"evaluation_id": str(ev.id), "gate": rep.technical_gate_passed, "pass_rate": rep.pass_rate,
                "failed": rep.failed}
