"""Editing sessions, timeline versions, renders, style profiles."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    AgentAction,
    AssetKind,
    AssetStatus,
    EditingSession,
    Evaluation,
    MediaAsset,
    Render,
    RenderStatus,
    SessionStatus,
    StyleProfile,
    TimelineVersion,
)
from db.session import get_db
from editing.operations import OPERATIONS, apply_action
from editing.timeline.schema import Timeline
from services.api.routes.projects import get_project
from services.api.schemas import EditCreate, EditDetail, EditOut, ManualAction, VersionOut
from services.worker.editing import ensure_style_profile, load_edit_context
from services.worker.jobs import enqueue_edit, enqueue_evaluation, enqueue_render

router = APIRouter(tags=["edits"])


def _session(sid: uuid.UUID, db: Session) -> EditingSession:
    e = db.get(EditingSession, sid)
    if e is None:
        raise HTTPException(404, f"editing session {sid} not found")
    return e


def _version(e: EditingSession, n: int | None) -> TimelineVersion:
    if not e.versions:
        raise HTTPException(409, "session has no timeline yet")
    if n is None:
        return e.versions[-1]
    v = next((v for v in e.versions if v.version == n), None)
    if v is None:
        raise HTTPException(404, f"version {n} not found (0-{e.versions[-1].version})")
    return v


@router.post("/projects/{project_id}/edits", response_model=EditOut, status_code=202)
def create_edit(project_id: uuid.UUID, body: EditCreate, db: Session = Depends(get_db)):
    project = get_project(project_id, db)
    if body.min_duration > body.max_duration:
        raise HTTPException(422, "min_duration must be <= max_duration")
    if body.source_asset_ids:
        sources = [db.get(MediaAsset, a) for a in body.source_asset_ids]
    else:
        sources = [a for a in project.assets if a.kind == AssetKind.source and a.status == AssetStatus.ready]
    bad = [str(a.id) for a in sources if a is None or a.project_id != project.id or a.status != AssetStatus.ready]
    if not sources or bad:
        raise HTTPException(422, f"need ready source assets in this project; not usable: {bad or 'none found'}")
    if body.reference_asset_id:
        ref = db.get(MediaAsset, body.reference_asset_id)
        if ref is None or ref.project_id != project.id or ref.status != AssetStatus.ready:
            raise HTTPException(422, "reference asset must be a ready asset in this project")
    e = EditingSession(project_id=project.id, instructions=body.instructions,
                       source_asset_ids=[str(a.id) for a in sources], reference_asset_id=body.reference_asset_id,
                       constraints={"min_duration": body.min_duration, "max_duration": body.max_duration})
    db.add(e)
    db.commit()
    enqueue_edit(e.id)
    db.refresh(e)
    return e


@router.get("/projects/{project_id}/edits", response_model=list[EditOut])
def list_edits(project_id: uuid.UUID, db: Session = Depends(get_db)):
    get_project(project_id, db)
    return db.scalars(select(EditingSession).where(EditingSession.project_id == project_id)
                      .order_by(EditingSession.created_at.desc())).all()


@router.get("/edits/{session_id}", response_model=EditDetail)
def read_edit(session_id: uuid.UUID, db: Session = Depends(get_db)):
    return _session(session_id, db)


@router.get("/edits/{session_id}/timeline", response_model=Timeline)
def read_timeline(session_id: uuid.UUID, version: int | None = None, db: Session = Depends(get_db)):
    return Timeline.model_validate(_version(_session(session_id, db), version).timeline)


@router.post("/edits/{session_id}/actions", response_model=VersionOut, status_code=201)
def manual_action(session_id: uuid.UUID, body: ManualAction, db: Session = Depends(get_db)):
    """Apply one editing operation by hand; same validation as the agent. Creates a new version."""
    e = _session(session_id, db)
    if e.status in (SessionStatus.queued, SessionStatus.running):
        raise HTTPException(409, "agent is still working on this session")
    if body.name not in OPERATIONS:
        raise HTTPException(422, f"unknown operation; valid: {', '.join(OPERATIONS)}")
    base = _version(e, None)
    ctx = load_edit_context(db, [uuid.UUID(x) for x in e.source_asset_ids], e.project_id)
    res = apply_action(Timeline.model_validate(base.timeline), body.name, body.args, ctx)
    step = (e.actions[-1].step + 1) if e.actions else 1
    new_n = base.version + 1 if res.changed else base.version
    db.add(AgentAction(session_id=e.id, step=step, name=body.name, args=body.args, source="user", ok=res.ok,
                       error=res.error, result=res.data if isinstance(res.data, dict | list) else None,
                       version_before=base.version, version_after=new_n, stage="user"))
    if not res.ok:
        db.commit()  # rejected actions are still logged
        raise HTTPException(422, res.error)
    if not res.changed:
        raise HTTPException(422, "operation does not change the timeline")
    v = TimelineVersion(session_id=e.id, version=new_n, parent_id=base.id, created_by="user",
                        timeline=res.timeline.model_dump(mode="json"), content_hash=res.timeline.content_hash(),
                        schema_version=res.timeline.schema_version)
    db.add(v)
    db.flush()
    db.refresh(v)
    return v


@router.post("/edits/{session_id}/render", status_code=202)
def rerender(session_id: uuid.UUID, version: int | None = None, db: Session = Depends(get_db)):
    """Render (or re-render) a stored version. Same timeline -> same render inputs (FR-06)."""
    v = _version(_session(session_id, db), version)
    problems = Timeline.model_validate(v.timeline).render_problems()
    if problems:
        raise HTTPException(422, "; ".join(problems))
    job = enqueue_render(v.id)
    return {"version": v.version, "job": job}


@router.get("/renders/{render_id}")
def read_render(render_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.get(Render, render_id)
    if r is None:
        raise HTTPException(404, "render not found")
    return {"id": r.id, "status": r.status, "duration": r.duration, "error": r.error, "meta": r.meta,
            "version": r.timeline_version.version, "session_id": r.timeline_version.session_id}


@router.get("/renders/{render_id}/video")
def render_video(render_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.get(Render, render_id)
    if r is None or r.status != RenderStatus.done or not r.path:
        raise HTTPException(404, "rendered video not available")
    return FileResponse(r.path, media_type="video/mp4", filename=f"render-{render_id}.mp4")


@router.post("/assets/{asset_id}/style-profile")
def build_style_profile(asset_id: uuid.UUID, db: Session = Depends(get_db)):
    a = db.get(MediaAsset, asset_id)
    if a is None or a.status != AssetStatus.ready:
        raise HTTPException(409, "asset must exist and be processed (status ready)")
    return ensure_style_profile(asset_id)


@router.get("/assets/{asset_id}/style-profile")
def read_style_profile(asset_id: uuid.UUID, db: Session = Depends(get_db)):
    p = db.scalar(select(StyleProfile).where(StyleProfile.asset_id == asset_id)
                  .order_by(StyleProfile.created_at.desc()))
    if p is None:
        raise HTTPException(404, "no style profile yet; POST to build one")
    return p.profile


@router.post("/renders/{render_id}/evaluate", status_code=202)
def evaluate_render(render_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.get(Render, render_id)
    if r is None or r.status != RenderStatus.done:
        raise HTTPException(404, "render not found or not finished")
    return {"render_id": render_id, "job": enqueue_evaluation(render_id)}


def _eval_summary(ev: Evaluation) -> dict:
    return {"id": ev.id, "render_id": ev.render_id, "version": ev.timeline_version.version,
            "evaluator_version": ev.evaluator_version, "judge_model": ev.judge_model,
            "technical_gate_passed": ev.technical_gate_passed, "pass_rate": ev.pass_rate,
            "by_category": ev.by_category, "failed": ev.report.get("failed", []), "trace_id": ev.trace_id,
            "created_at": ev.created_at}


@router.get("/edits/{session_id}/evaluations")
def list_evaluations(session_id: uuid.UUID, db: Session = Depends(get_db)):
    _session(session_id, db)
    evs = db.scalars(select(Evaluation).where(Evaluation.session_id == session_id)
                     .order_by(Evaluation.created_at)).all()
    return [_eval_summary(ev) for ev in evs]


@router.get("/evaluations/{evaluation_id}")
def read_evaluation(evaluation_id: uuid.UUID, db: Session = Depends(get_db)):
    ev = db.get(Evaluation, evaluation_id)
    if ev is None:
        raise HTTPException(404, "evaluation not found")
    return _eval_summary(ev) | {"report": ev.report}
