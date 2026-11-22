"""API request/response models (kept separate from DB models on purpose)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class StageOut(ORM):
    name: str
    status: str
    attempts: int
    error: str | None
    tool_version: str | None
    detail: dict | None
    started_at: datetime | None
    finished_at: datetime | None


class AssetOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    status: str
    original_filename: str
    size_bytes: int
    sha256: str
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    aspect_ratio: str | None
    has_audio: bool | None
    language: str | None
    last_error: str | None
    created_at: datetime


class AssetDetail(AssetOut):
    audio_features: dict | None
    stages: list[StageOut]


class ProjectOut(ORM):
    id: uuid.UUID
    title: str
    description: str | None
    created_at: datetime


class ProjectDetail(ProjectOut):
    assets: list[AssetOut]


class SceneOut(ORM):
    id: uuid.UUID
    asset_id: uuid.UUID
    index: int
    start: float
    end: float
    description: str | None
    tags: list[str]
    speech_ratio: float
    transcript_text: str | None
    vision_model: str | None


class SegmentOut(ORM):
    start: float
    end: float
    text: str
    words: list | None


class SearchHit(BaseModel):
    scene: SceneOut
    score: float
    matched_by: list[str]  # "keyword", "semantic"


class EditCreate(BaseModel):
    instructions: str = Field(min_length=5, max_length=4000)
    source_asset_ids: list[uuid.UUID] | None = Field(default=None, description="default: all ready source assets")
    reference_asset_id: uuid.UUID | None = None
    min_duration: float = Field(default=15, ge=3, le=180)
    max_duration: float = Field(default=30, ge=3, le=180)


class RenderOut(ORM):
    id: uuid.UUID
    status: str
    duration: float | None
    error: str | None
    created_at: datetime


class VersionOut(ORM):
    version: int
    content_hash: str
    created_by: str
    created_at: datetime
    renders: list[RenderOut]


class ActionOut(ORM):
    step: int
    name: str
    args: dict
    source: str
    ok: bool
    error: str | None
    version_before: int | None
    version_after: int | None
    stage: str | None


class EditOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    instructions: str
    status: str
    reference_asset_id: uuid.UUID | None
    constraints: dict | None
    agent_version: str | None
    error: str | None
    trace_id: str | None
    created_at: datetime


class EditDetail(EditOut):
    source_asset_ids: list[str]
    creator_id: uuid.UUID | None
    context_tags: list[str] | None
    memory_used: list | None
    agent_config: dict | None
    plan: dict | None
    versions: list[VersionOut]
    actions: list[ActionOut]


class ManualAction(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)
