"""Phase 1 schema: creators, projects, media assets, processing stages, scenes, transcripts.

Conventions
- UUID primary keys (safe to expose in URLs, generated app-side).
- Source media rows are never mutated after ingest except for status/analysis fields;
  the file on disk is immutable (PRD §7.3).
- Every analysis artefact records the tool/model version that produced it (NFR-09).
"""

import enum
import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from config.settings import get_settings

EMBED_DIM = get_settings().embedding_dim


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSONB}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    handle: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(128))


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)

    assets: Mapped[list["MediaAsset"]] = relationship(back_populates="project", order_by="MediaAsset.created_at")


class AssetKind(enum.StrEnum):
    source = "source"
    reference = "reference"


class AssetStatus(enum.StrEnum):
    uploaded = "uploaded"
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class MediaAsset(TimestampMixin, Base):
    __tablename__ = "media_assets"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[AssetKind] = mapped_column(Enum(AssetKind, name="asset_kind"))
    status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus, name="asset_status"), default=AssetStatus.uploaded)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(1024))  # immutable source file
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)

    # technical metadata (ffprobe)
    duration: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    aspect_ratio: Mapped[str | None] = mapped_column(String(16))
    has_audio: Mapped[bool | None]
    probe: Mapped[dict | None]  # full MediaMetadata

    # audio analysis: loudness + silences
    audio_features: Mapped[dict | None]
    language: Mapped[str | None] = mapped_column(String(16))

    last_error: Mapped[str | None] = mapped_column(Text)
    rq_job_id: Mapped[str | None] = mapped_column(String(64))

    project: Mapped[Project] = relationship(back_populates="assets")
    stages: Mapped[list["ProcessingStage"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", order_by="ProcessingStage.position")
    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", order_by="Scene.index")
    transcript: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", order_by="TranscriptSegment.start")


class StageStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    skipped = "skipped"


class ProcessingStage(Base):
    """One row per (asset, stage). The pipeline skips `done` stages, which makes re-runs resume."""

    __tablename__ = "processing_stages"
    __table_args__ = (UniqueConstraint("asset_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(32))
    position: Mapped[int]
    status: Mapped[StageStatus] = mapped_column(Enum(StageStatus, name="stage_status"), default=StageStatus.pending)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    tool_version: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[dict | None]  # small stage summary (counts, timings)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    asset: Mapped[MediaAsset] = relationship(back_populates="stages")


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("asset_id", "index"),
        Index("ix_scenes_search", "search_tsv", postgresql_using="gin"),
        Index("ix_scenes_embedding", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"), index=True)
    index: Mapped[int]
    start: Mapped[float]
    end: Mapped[float]
    frame_path: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    speech_ratio: Mapped[float] = mapped_column(default=0.0)
    transcript_text: Mapped[str | None] = mapped_column(Text)  # denormalised for search/prompts
    features: Mapped[dict | None]  # mean luma, motion etc. (extensible)
    vision_model: Mapped[str | None] = mapped_column(String(128))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    # description + tags + transcript, written by the pipeline; Postgres derives the tsvector
    search_text: Mapped[str | None] = mapped_column(Text)
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english'::regconfig, coalesce(search_text, ''))", persisted=True))

    asset: Mapped[MediaAsset] = relationship(back_populates="scenes")

    @property
    def duration(self) -> float:
        return self.end - self.start


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"), index=True)
    start: Mapped[float]
    end: Mapped[float]
    text: Mapped[str] = mapped_column(Text)
    words: Mapped[list | None] = mapped_column(JSONB)  # [{start,end,text,probability}]
    asr_model: Mapped[str | None] = mapped_column(String(64))

    asset: Mapped[MediaAsset] = relationship(back_populates="transcript")


# ============================================================ Phase 2: editing
class SessionStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    rendered = "rendered"
    failed = "failed"


class EditingSession(TimestampMixin, Base):
    """One request to produce an edit: instructions + inputs -> timeline versions -> renders."""

    __tablename__ = "editing_sessions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    instructions: Mapped[str] = mapped_column(Text)
    source_asset_ids: Mapped[list[str]] = mapped_column(ARRAY(String(36)))
    reference_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media_assets.id"))
    constraints: Mapped[dict | None]          # min/max duration etc.
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus, name="session_status"),
                                                  default=SessionStatus.queued)
    agent_version: Mapped[str | None] = mapped_column(String(64))
    agent_config: Mapped[dict | None]         # models, prompt hashes, budgets (NFR-09)
    plan: Mapped[dict | None]                 # the structured EditPlan the planner produced
    error: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64))  # LangSmith root run id
    creator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    context_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(48)))
    memory_used: Mapped[list | None] = mapped_column(JSONB)  # preferences that shaped this session

    versions: Mapped[list["TimelineVersion"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="TimelineVersion.version")
    actions: Mapped[list["AgentAction"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="AgentAction.step")


class TimelineVersion(Base):
    """Immutable snapshot. Every successful timeline change creates a new row (FR-06)."""

    __tablename__ = "timeline_versions"
    __table_args__ = (UniqueConstraint("session_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("editing_sessions.id", ondelete="CASCADE"))
    version: Mapped[int]
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("timeline_versions.id"))
    timeline: Mapped[dict]
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[str] = mapped_column(String(32))  # agent | user
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped[EditingSession] = relationship(back_populates="versions")
    renders: Mapped[list["Render"]] = relationship(back_populates="timeline_version", order_by="Render.created_at")


class AgentAction(Base):
    """Audit log of every attempted operation, including rejected ones (FR-06: all actions logged)."""

    __tablename__ = "agent_actions"
    __table_args__ = (UniqueConstraint("session_id", "step"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("editing_sessions.id", ondelete="CASCADE"))
    step: Mapped[int]
    name: Mapped[str] = mapped_column(String(48))
    args: Mapped[dict]
    source: Mapped[str] = mapped_column(String(16))  # plan | repair | user | fixup
    ok: Mapped[bool]
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None]
    version_before: Mapped[int | None]
    version_after: Mapped[int | None]
    stage: Mapped[str | None] = mapped_column(String(32))  # workflow stage, for next-action prediction
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped[EditingSession] = relationship(back_populates="actions")


class RenderStatus(enum.StrEnum):
    done = "done"
    failed = "failed"


class Render(Base):
    __tablename__ = "renders"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    timeline_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("timeline_versions.id", ondelete="CASCADE"),
                                                           index=True)
    status: Mapped[RenderStatus] = mapped_column(Enum(RenderStatus, name="render_status"))
    path: Mapped[str | None] = mapped_column(String(1024))
    duration: Mapped[float | None]
    meta: Mapped[dict | None]  # argv, hashes, ffmpeg/renderer versions, loudness, probe
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    timeline_version: Mapped[TimelineVersion] = relationship(back_populates="renders")


class StyleProfile(Base):
    """Measured editing characteristics of a reference asset (FR-04)."""

    __tablename__ = "style_profiles"
    __table_args__ = (UniqueConstraint("asset_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(32))  # extractor version
    profile: Mapped[dict]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ============================================================ Phase 3: evaluation
class Evaluation(Base):
    """One independent evaluation of one render (FR-09). Linked to its timeline version."""

    __tablename__ = "evaluations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    render_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("renders.id", ondelete="CASCADE"), index=True)
    timeline_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("timeline_versions.id", ondelete="CASCADE"),
                                                           index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("editing_sessions.id", ondelete="CASCADE"), index=True)
    evaluator_version: Mapped[str] = mapped_column(String(32))
    judge_model: Mapped[str | None] = mapped_column(String(128))
    technical_gate_passed: Mapped[bool]
    pass_rate: Mapped[float]
    by_category: Mapped[dict]
    report: Mapped[dict]
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    issues: Mapped[list["EvaluationIssue"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")
    timeline_version: Mapped[TimelineVersion] = relationship()


class EvaluationIssue(Base):
    """A failed check, one row each — the raw material for failure clustering (Phase 5)."""

    __tablename__ = "evaluation_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"), index=True)
    check_id: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list | None] = mapped_column(JSONB)
    start: Mapped[float | None]
    end: Mapped[float | None]

    evaluation: Mapped[Evaluation] = relationship(back_populates="issues")


# ============================================================ Phase 4: creator memory + prediction
class PreferenceSource(enum.StrEnum):
    explicit = "explicit"      # the creator stated it directly (settings / API)
    feedback = "feedback"      # extracted from feedback on an edit
    inferred = "inferred"      # inferred from behaviour (e.g. repeated manual corrections)


class PreferenceStatus(enum.StrEnum):
    candidate = "candidate"    # seen, not trusted yet: never applied
    active = "active"          # applied when relevant
    session = "session"        # applies only to one editing session
    rejected = "rejected"      # creator said no: never applied, not re-proposed
    stale = "stale"            # contradicted; needs confirmation before use again


class CreatorPreference(TimestampMixin, Base):
    __tablename__ = "creator_preferences"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)   # captions, color, pacing, duration, ...
    attribute: Mapped[str] = mapped_column(String(64), index=True)  # normalised key, e.g. caption_position
    value: Mapped[str] = mapped_column(String(160))                 # e.g. "top"; conflicts = same attr, other value
    statement: Mapped[str] = mapped_column(Text)                    # "Captions in ALL CAPS at the top"
    context: Mapped[list[str]] = mapped_column(ARRAY(String(48)), default=list)  # [] = applies everywhere
    source: Mapped[PreferenceSource] = mapped_column(Enum(PreferenceSource, name="preference_source"))
    status: Mapped[PreferenceStatus] = mapped_column(Enum(PreferenceStatus, name="preference_status"))
    confidence: Mapped[float]
    support_count: Mapped[int] = mapped_column(default=1)
    contradict_count: Mapped[int] = mapped_column(default=0)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("editing_sessions.id", ondelete="CASCADE"))
    evidence: Mapped[list] = mapped_column(JSONB, default=list)    # [{feedback_id, session_id, quote}]
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))

    events: Mapped[list["PreferenceEvent"]] = relationship(back_populates="preference", cascade="all, delete-orphan",
                                                           order_by="PreferenceEvent.id")


class PreferenceEvent(Base):
    """Audit log: every change to a preference and why (FR-08: updates are auditable)."""

    __tablename__ = "preference_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    preference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creator_preferences.id", ondelete="CASCADE"),
                                                     index=True)
    kind: Mapped[str] = mapped_column(String(24))  # created, reinforced, contradicted, confirmed, rejected, edited
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence_before: Mapped[float | None]
    confidence_after: Mapped[float | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    preference: Mapped[CreatorPreference] = relationship(back_populates="events")


class FeedbackKind(enum.StrEnum):
    accept = "accept"
    reject = "reject"
    choose = "choose"              # picked one of two renders
    comment = "comment"            # free text
    timestamp_issue = "timestamp_issue"
    correction = "correction"      # "the captions should be at the top"


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("editing_sessions.id", ondelete="CASCADE"), index=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    timeline_version: Mapped[int | None]
    render_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("renders.id"))
    kind: Mapped[FeedbackKind] = mapped_column(Enum(FeedbackKind, name="feedback_kind"))
    text: Mapped[str | None] = mapped_column(Text)
    start: Mapped[float | None]
    end: Mapped[float | None]
    chosen_render_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("renders.id"))
    other_render_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("renders.id"))
    processed: Mapped[dict | None] = mapped_column(JSONB)  # memory-graph outcome
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MemoryConfirmation(Base):
    """A question the memory graph is waiting on (a LangGraph interrupt, resumable by thread_id)."""

    __tablename__ = "memory_confirmations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    preference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creator_preferences.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | answered
    answer: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ActionPrediction(Base):
    """A next-action prediction and the action that actually happened (FR-07: results stored)."""

    __tablename__ = "action_predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("editing_sessions.id", ondelete="CASCADE"),
                                                         index=True)
    step: Mapped[int]
    predictor: Mapped[str] = mapped_column(String(48))  # rules-v1 | llm:<model> | learned:<hash>
    mode: Mapped[str] = mapped_column(String(16))       # online | offline
    predicted: Mapped[list[str]] = mapped_column(ARRAY(String(48)))
    actual: Mapped[str] = mapped_column(String(48))
    stage: Mapped[str | None] = mapped_column(String(32))
    correct_top1: Mapped[bool]
    correct_top3: Mapped[bool]
    valid: Mapped[bool]
    latency_ms: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
