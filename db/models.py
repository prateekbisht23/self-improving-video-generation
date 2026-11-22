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
