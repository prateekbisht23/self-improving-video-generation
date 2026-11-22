"""Feedback (FR-10) and creator memory (FR-08)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.graphs import memory_graph
from db.models import (
    CreatorPreference,
    EditingSession,
    Feedback,
    FeedbackKind,
    MemoryConfirmation,
    PreferenceStatus,
    Render,
    User,
)
from db.session import get_db
from memory import storage
from services.api.routes.projects import current_user

router = APIRouter(tags=["memory"])


class FeedbackIn(BaseModel):
    kind: FeedbackKind
    text: str | None = Field(default=None, max_length=4000)
    version: int | None = Field(default=None, description="timeline version; default latest")
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    chosen_render_id: uuid.UUID | None = None
    other_render_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _shape(self):
        if self.kind in (FeedbackKind.comment, FeedbackKind.correction, FeedbackKind.timestamp_issue) and not self.text:
            raise ValueError(f"{self.kind.value} feedback needs text")
        if self.kind == FeedbackKind.timestamp_issue and self.start is None:
            raise ValueError("timestamp_issue needs start")
        if self.kind == FeedbackKind.choose and not (self.chosen_render_id and self.other_render_id):
            raise ValueError("choose needs chosen_render_id and other_render_id")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("end must be >= start")
        return self


class PreferenceIn(BaseModel):
    statement: str = Field(min_length=3, max_length=300)
    category: str | None = None
    attribute: str | None = None
    value: str | None = None
    context: list[str] = Field(default_factory=list)


class PreferencePatch(BaseModel):
    status: Literal["active", "rejected"]


class Answers(BaseModel):
    answers: dict[str, Literal["confirm", "reject"]]


def _pref_out(p: CreatorPreference) -> dict:
    return {"id": p.id, "category": p.category, "attribute": p.attribute, "value": p.value,
            "statement": p.statement, "context": p.context, "source": p.source, "status": p.status,
            "confidence": p.confidence, "support_count": p.support_count, "contradict_count": p.contradict_count,
            "session_id": p.session_id, "last_seen_at": p.last_seen_at, "confirmed_at": p.confirmed_at,
            "evidence": p.evidence}


@router.post("/edits/{session_id}/feedback", status_code=201)
def give_feedback(session_id: uuid.UUID, body: FeedbackIn, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    e = db.get(EditingSession, session_id)
    if e is None:
        raise HTTPException(404, "editing session not found")
    if not e.versions:
        raise HTTPException(409, "session has no timeline to give feedback on")
    v = e.versions[-1] if body.version is None else next((x for x in e.versions if x.version == body.version), None)
    if v is None:
        raise HTTPException(404, f"version {body.version} not found")
    total = sum(c["src_out"] - c["src_in"] for c in v.timeline["video"]) - sum(
        c.get("transition_duration", 0) for c in v.timeline["video"][1:])
    for t in (body.start, body.end):
        if t is not None and t > total + 0.05:
            raise HTTPException(422, f"timestamp {t}s is outside the edit (0-{total:.2f}s)")
    for rid in (body.chosen_render_id, body.other_render_id):
        r = db.get(Render, rid) if rid else None
        if rid and (r is None or r.timeline_version.session.project_id != e.project_id):
            raise HTTPException(422, f"render {rid} not found in this project")
    render = v.renders[-1] if v.renders else None
    f = Feedback(session_id=e.id, creator_id=e.creator_id or user.id, timeline_version=v.version,
                 render_id=render.id if render else None, kind=body.kind, text=body.text, start=body.start,
                 end=body.end, chosen_render_id=body.chosen_render_id, other_render_id=body.other_render_id)
    db.add(f)
    db.commit()
    return {"feedback_id": f.id, "memory": memory_graph.process_feedback(f.id)}


@router.get("/creators/me/preferences")
def list_preferences(status: PreferenceStatus | None = None, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    q = select(CreatorPreference).where(CreatorPreference.creator_id == user.id)
    if status:
        q = q.where(CreatorPreference.status == status)
    return [_pref_out(p) for p in db.scalars(q.order_by(CreatorPreference.updated_at.desc()))]


@router.post("/creators/me/preferences", status_code=201)
def add_preference(body: PreferenceIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    cat, attr, val = body.category, body.attribute, body.value
    if not (cat and attr and val):  # normalise the statement into category/attribute/value
        from memory.extraction import extract

        c = next(iter(extract(body.statement, "explicit")), None)
        if c is None:
            raise HTTPException(422, "could not read an editing preference from that statement")
        cat, attr, val = cat or c.category, attr or c.attribute, val or c.value
    p = storage.add_explicit(db, user.id, category=cat, attribute=attr, value=val, statement=body.statement,
                             context=body.context)
    return _pref_out(p)


@router.patch("/creators/me/preferences/{pref_id}")
def set_preference_status(pref_id: uuid.UUID, body: PreferencePatch, db: Session = Depends(get_db),
                          user: User = Depends(current_user)):
    p = db.get(CreatorPreference, pref_id)
    if p is None or p.creator_id != user.id:
        raise HTTPException(404, "preference not found")
    (storage.confirm if body.status == "active" else storage.reject)(db, p, by="creator_settings")
    return _pref_out(p)


@router.get("/creators/me/preferences/{pref_id}/events")
def preference_history(pref_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(CreatorPreference, pref_id)
    if p is None or p.creator_id != user.id:
        raise HTTPException(404, "preference not found")
    return [{"kind": e.kind, "detail": e.detail, "confidence_before": e.confidence_before,
             "confidence_after": e.confidence_after, "at": e.created_at} for e in p.events]


@router.get("/memory/confirmations")
def pending_confirmations(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(MemoryConfirmation).where(MemoryConfirmation.creator_id == user.id,
                                                       MemoryConfirmation.status == "pending")
                      .order_by(MemoryConfirmation.created_at)).all()
    return [{"thread_id": r.thread_id, "preference_id": r.preference_id, "question": r.question,
             "created_at": r.created_at} for r in rows]


@router.post("/memory/confirmations/{thread_id}")
def answer_confirmations(thread_id: str, body: Answers, db: Session = Depends(get_db),
                         user: User = Depends(current_user)):
    pending = db.scalars(select(MemoryConfirmation).where(MemoryConfirmation.thread_id == thread_id,
                                                          MemoryConfirmation.status == "pending")).all()
    if not pending:
        raise HTTPException(404, "no pending questions for this thread")
    if any(r.creator_id != user.id for r in pending):
        raise HTTPException(403, "not your confirmation")
    unknown = set(body.answers) - {str(r.preference_id) for r in pending}
    if unknown:
        raise HTTPException(422, f"not asked in this thread: {sorted(unknown)}")
    db.commit()  # release locks before the graph writes
    return memory_graph.resume(thread_id, body.answers)
