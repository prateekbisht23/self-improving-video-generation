"""Timeline v0 — the single source of truth the renderer consumes.

An LLM never produces ffmpeg commands; it produces (via typed tools) a Timeline, which is
validated here and later compiled deterministically into an ffmpeg filtergraph.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "0.1"


class OutputSpec(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    min_duration: float = 15.0
    max_duration: float = 30.0

    @property
    def aspect_ratio(self) -> str:
        from math import gcd

        g = gcd(self.width, self.height)
        return f"{self.width // g}:{self.height // g}"


class AssetRef(BaseModel):
    id: str
    path: str
    duration: float = Field(gt=0)


class VideoClip(BaseModel):
    asset_id: str
    src_in: float = Field(ge=0)
    src_out: float = Field(gt=0)
    transition_in: Literal["cut", "fade", "dissolve"] = "cut"
    transition_duration: float = Field(default=0.0, ge=0, le=1.5)
    volume: float = Field(default=1.0, ge=0, le=4.0)
    scene_id: str | None = None  # provenance: which analysed scene this came from

    @model_validator(mode="after")
    def _order(self):
        if self.src_out <= self.src_in:
            raise ValueError(f"src_out ({self.src_out}) must be > src_in ({self.src_in})")
        return self

    @property
    def duration(self) -> float:
        return self.src_out - self.src_in


class Caption(BaseModel):
    start: float = Field(ge=0)  # timeline time, not source time
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=200)
    position: Literal["top", "center", "bottom"] = "bottom"


class Timeline(BaseModel):
    schema_version: str = SCHEMA_VERSION
    output: OutputSpec = OutputSpec()
    assets: list[AssetRef]
    video: list[VideoClip] = Field(min_length=1)
    captions: list[Caption] = Field(default_factory=list)
    music_volume: float = Field(default=0.0, ge=0, le=1.0)

    @property
    def duration(self) -> float:
        # transitions overlap adjacent clips
        return sum(c.duration for c in self.video) - sum(
            c.transition_duration for c in self.video[1:] if c.transition_in != "cut")

    @model_validator(mode="after")
    def _validate_refs(self):
        assets = {a.id: a for a in self.assets}
        errors = []
        for i, c in enumerate(self.video):
            a = assets.get(c.asset_id)
            if a is None:
                errors.append(f"video[{i}]: unknown asset '{c.asset_id}'")
            elif c.src_out > a.duration + 1e-3:
                errors.append(f"video[{i}]: src_out {c.src_out}s beyond asset duration {a.duration}s")
            if i > 0 and c.transition_duration >= min(c.duration, self.video[i - 1].duration):
                errors.append(f"video[{i}]: transition longer than adjacent clip")
        total = self.duration
        for i, cap in enumerate(self.captions):
            if cap.end <= cap.start:
                errors.append(f"captions[{i}]: end must be > start")
            if cap.end > total + 1e-3:
                errors.append(f"captions[{i}]: ends at {cap.end}s past timeline end {total:.2f}s")
        if errors:
            raise ValueError("; ".join(errors))
        return self
