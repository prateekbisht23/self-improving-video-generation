"""Retrieve the preferences that should shape one editing session.

1. Candidates: active preferences of the creator + session-scoped ones for this session.
2. Context filter: a preference scoped to contexts (e.g. ['interview']) applies only if the session
   shares one of them; unscoped preferences apply everywhere.
3. Conflict resolution per attribute: session > context-specific > generic, then confidence, then recency.
4. Every returned item carries the reason it was chosen; dropped conflicts are reported too.
"""

import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from db.models import CreatorPreference, PreferenceStatus


@dataclass
class Retrieved:
    id: str
    category: str
    attribute: str
    value: str
    statement: str
    confidence: float
    scope: str           # session | context | generic
    reason: str

    def as_prompt(self) -> str:
        return f"{self.statement} (confidence {self.confidence:.2f}; {self.scope})"

    def to_dict(self) -> dict:
        return asdict(self)


def retrieve(s: Session, creator_id: uuid.UUID, context_tags: list[str],
             session_id: uuid.UUID | None = None, limit: int = 12) -> tuple[list[Retrieved], list[dict]]:
    q = select(CreatorPreference).where(
        CreatorPreference.creator_id == creator_id,
        or_(CreatorPreference.status == PreferenceStatus.active,
            (CreatorPreference.status == PreferenceStatus.session) & (CreatorPreference.session_id == session_id)))
    tags = set(context_tags)
    best: dict[str, tuple[tuple, CreatorPreference, str]] = {}
    dropped: list[dict] = []
    for p in s.scalars(q):
        if p.context and not tags & set(p.context):
            dropped.append({"id": str(p.id), "statement": p.statement,
                            "why": f"context {p.context} does not match session {sorted(tags)}"})
            continue
        scope = "session" if p.status == PreferenceStatus.session else "context" if p.context else "generic"
        rank = ({"session": 2, "context": 1, "generic": 0}[scope], p.confidence, p.last_seen_at.timestamp())
        cur = best.get(p.attribute)
        if cur is None or rank > cur[0]:
            if cur:
                dropped.append({"id": str(cur[1].id), "statement": cur[1].statement,
                                "why": f"conflict on '{p.attribute}': lost to '{p.statement}'"})
            best[p.attribute] = (rank, p, scope)
        else:
            dropped.append({"id": str(p.id), "statement": p.statement,
                            "why": f"conflict on '{p.attribute}': lost to '{cur[1].statement}'"})
    chosen = sorted(best.values(), key=lambda t: t[0], reverse=True)[:limit]
    return [Retrieved(id=str(p.id), category=p.category, attribute=p.attribute, value=p.value,
                      statement=p.statement, confidence=p.confidence, scope=scope,
                      reason={"session": "said for this session", "context": f"matches context {p.context}",
                              "generic": "applies to all videos"}[scope])
            for _, p, scope in chosen], dropped
