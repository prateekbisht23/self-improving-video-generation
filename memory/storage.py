"""Preference storage with confidence, evidence, recency and an audit trail.

Confidence policy (documented in docs/learn/15):
- explicit (creator stated it in settings)             -> active, 0.90
- feedback, general wording ("always", "never")         -> candidate 0.50, ask for confirmation
- feedback, plain correction                            -> candidate 0.35 (never applied)
- reinforced by another session                         -> +0.15; at support >= 2 ask for confirmation
- contradicted                                          -> -0.25; an active one below 0.5 becomes stale
- confirmed by the creator                              -> active, max(conf, 0.85)
- rejected by the creator                               -> rejected (never applied, not re-proposed)
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import get_settings
from db.models import CreatorPreference, PreferenceEvent, PreferenceSource, PreferenceStatus

ACTIVE_FLOOR = 0.5


def _now():
    return datetime.now(UTC)


def _embed(text: str) -> list[float] | None:
    if not get_settings().pipeline_embeddings:
        return None
    from config.models import get_embeddings

    return get_embeddings().embed_documents([text], task_type="RETRIEVAL_DOCUMENT")[0]


def log_event(s: Session, p: CreatorPreference, event: str, before: float | None, **detail) -> None:
    s.add(PreferenceEvent(preference_id=p.id, kind=event, detail=detail, confidence_before=before,
                          confidence_after=p.confidence))


def add_preference(s: Session, *, creator_id: uuid.UUID, category: str, attribute: str, value: str,
                   statement: str, source: PreferenceSource, status: PreferenceStatus, confidence: float,
                   context: list[str] | None = None, session_id: uuid.UUID | None = None,
                   evidence: dict | None = None) -> CreatorPreference:
    p = CreatorPreference(creator_id=creator_id, category=category, attribute=attribute, value=value,
                          statement=statement, source=source, status=status, confidence=round(confidence, 3),
                          context=sorted(set(context or [])), session_id=session_id,
                          evidence=[evidence] if evidence else [], embedding=_embed(f"{category}: {statement}"))
    s.add(p)
    s.flush()
    log_event(s, p, "created", None, source=source.value, status=status.value, **(evidence or {}))
    return p


def add_explicit(s: Session, creator_id: uuid.UUID, *, category: str, attribute: str, value: str, statement: str,
                 context: list[str] | None = None) -> CreatorPreference:
    """A preference the creator stated directly. Replaces an active one for the same attribute+context."""
    for old in same_attribute(s, creator_id, attribute, statuses=(PreferenceStatus.active,)):
        if sorted(old.context) == sorted(set(context or [])) and old.value != value:
            before = old.confidence
            old.status = PreferenceStatus.stale
            log_event(s, old, "superseded", before, by_statement=statement)
    return add_preference(s, creator_id=creator_id, category=category, attribute=attribute, value=value,
                          statement=statement, source=PreferenceSource.explicit, status=PreferenceStatus.active,
                          confidence=0.9, context=context, evidence={"kind": "explicit"})


def same_attribute(s: Session, creator_id, attribute: str, statuses=None) -> list[CreatorPreference]:
    q = select(CreatorPreference).where(CreatorPreference.creator_id == creator_id,
                                        CreatorPreference.attribute == attribute,
                                        CreatorPreference.session_id.is_(None))
    if statuses:
        q = q.where(CreatorPreference.status.in_(statuses))
    return list(s.scalars(q))


def reinforce(s: Session, p: CreatorPreference, evidence: dict) -> None:
    before = p.confidence
    p.support_count += 1
    p.confidence = round(min(0.95, p.confidence + 0.15), 3)
    p.evidence = [*p.evidence, evidence]
    p.last_seen_at = _now()
    log_event(s, p, "reinforced", before, **evidence)


def contradict(s: Session, p: CreatorPreference, evidence: dict) -> None:
    before = p.confidence
    p.contradict_count += 1
    p.confidence = round(max(0.05, p.confidence - 0.25), 3)
    p.evidence = [*p.evidence, {**evidence, "contradicts": True}]
    if p.status == PreferenceStatus.active and p.confidence < ACTIVE_FLOOR:
        p.status = PreferenceStatus.stale
    log_event(s, p, "contradicted", before, **evidence)


def confirm(s: Session, p: CreatorPreference, by: str = "creator") -> None:
    before = p.confidence
    p.status, p.confidence, p.confirmed_at = PreferenceStatus.active, round(max(p.confidence, 0.85), 3), _now()
    log_event(s, p, "confirmed", before, by=by)
    for other in same_attribute(s, p.creator_id, p.attribute, statuses=(PreferenceStatus.active,)):
        if other.id != p.id and sorted(other.context) == sorted(p.context) and other.value != p.value:
            b = other.confidence
            other.status = PreferenceStatus.stale
            log_event(s, other, "superseded", b, by_preference=str(p.id))


def reject(s: Session, p: CreatorPreference, by: str = "creator") -> None:
    before = p.confidence
    p.status = PreferenceStatus.rejected
    log_event(s, p, "rejected", before, by=by)
