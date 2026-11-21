"""Structured media context (PRD FR-03 expected output)."""

from pydantic import BaseModel, Field


class StreamInfo(BaseModel):
    index: int
    codec_type: str
    codec_name: str | None = None


class MediaMetadata(BaseModel):
    path: str
    duration: float
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    aspect_ratio: str | None = None
    has_audio: bool
    has_video: bool
    size_bytes: int
    streams: list[StreamInfo]


class Word(BaseModel):
    start: float
    end: float
    text: str
    probability: float | None = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[Word] = Field(default_factory=list)


class SilenceRange(BaseModel):
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


class AudioFeatures(BaseModel):
    integrated_lufs: float | None = None
    loudness_range_lu: float | None = None
    true_peak_dbfs: float | None = None
    silences: list[SilenceRange] = Field(default_factory=list)


class SceneDescription(BaseModel):
    """What the vision model returns for one representative frame."""

    description: str = Field(description="One or two sentences describing what is visible.")
    tags: list[str] = Field(description="3-8 short lowercase visual tags (objects, setting, shot type).")


class Scene(BaseModel):
    id: str
    index: int
    start: float
    end: float
    frame_path: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    speech_ratio: float = 0.0  # share of the scene covered by speech

    @property
    def duration(self) -> float:
        return self.end - self.start


class MediaContext(BaseModel):
    schema_version: str = "0.1"
    metadata: MediaMetadata
    audio: AudioFeatures
    transcript: list[TranscriptSegment]
    scenes: list[Scene]
    language: str | None = None
