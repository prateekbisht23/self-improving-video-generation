"""Timeline v1 — the single source of truth the renderer consumes.

An LLM never produces ffmpeg commands; it produces (via typed operations) a Timeline, which is
validated here and compiled deterministically into an ffmpeg filtergraph by `rendering/`.

Time domains
- source time: seconds inside an asset (`src_in`, `src_out`)
- timeline time: seconds in the output video (captions, titles). Transitions overlap adjacent
  clips, so clip i starts at  start(i-1) + dur(i-1) - transition(i).
"""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.0"

Transition = Literal["cut", "fade", "dissolve", "wipeleft", "slideup", "fadeblack"]
ColorPreset = Literal["none", "warm", "cool", "vivid", "muted", "bw"]
Position = Literal["top", "center", "bottom"]


class OutputSpec(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    min_duration: float = Field(default=15.0, ge=1)
    max_duration: float = Field(default=30.0, ge=1)
    loudness_lufs: float = Field(default=-14.0, ge=-30, le=-8)  # short-form platforms ~ -14

    @property
    def aspect_ratio(self) -> str:
        from math import gcd

        g = gcd(self.width, self.height)
        return f"{self.width // g}:{self.height // g}"


class AssetRef(BaseModel):
    id: str
    path: str
    duration: float = Field(gt=0)
    width: int | None = None
    height: int | None = None
    has_audio: bool = True


class VideoClip(BaseModel):
    asset_id: str
    src_in: float = Field(ge=0)
    src_out: float = Field(gt=0)
    transition_in: Transition = "cut"
    transition_duration: float = Field(default=0.0, ge=0, le=1.5)
    volume: float = Field(default=1.0, ge=0, le=4.0)
    crop_x: float = Field(default=0.5, ge=0, le=1, description="horizontal centre of the 9:16 crop window")
    scene_id: str | None = None  # provenance: which analysed scene this came from
    purpose: str | None = Field(default=None, max_length=200)  # why the agent chose it

    @model_validator(mode="after")
    def _order(self):
        if self.src_out <= self.src_in:
            raise ValueError(f"src_out ({self.src_out}) must be > src_in ({self.src_in})")
        if self.transition_in == "cut":
            self.transition_duration = 0.0
        elif self.transition_duration == 0:
            self.transition_duration = 0.4
        return self

    @property
    def duration(self) -> float:
        return self.src_out - self.src_in


class Caption(BaseModel):
    start: float = Field(ge=0)  # timeline time, not source time
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=200)


class Title(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=80)


class CaptionStyle(BaseModel):
    position: Position = "bottom"
    font: str = "Helvetica Neue"
    size: int = Field(default=80, ge=20, le=160)  # px at 1080x1920
    color: str = Field(default="FFFFFF", pattern=r"^[0-9A-Fa-f]{6}$")
    highlight: str = Field(default="FFD400", pattern=r"^[0-9A-Fa-f]{6}$")
    outline: int = Field(default=5, ge=0, le=12)
    uppercase: bool = False
    max_words: int = Field(default=4, ge=1, le=12)


class Style(BaseModel):
    color: ColorPreset = "none"
    captions: CaptionStyle = CaptionStyle()


class Timeline(BaseModel):
    schema_version: str = SCHEMA_VERSION
    output: OutputSpec = OutputSpec()
    assets: list[AssetRef]
    video: list[VideoClip] = Field(default_factory=list)  # may be empty while being built
    captions: list[Caption] = Field(default_factory=list)
    titles: list[Title] = Field(default_factory=list)
    style: Style = Style()
    # "transcript": captions are derived from word timestamps and regenerated whenever clips change
    captions_source: Literal["none", "transcript", "manual"] = "none"

    # ------------------------------------------------------------ derived
    def clip_starts(self) -> list[float]:
        """Timeline start of each clip (transitions overlap the previous clip's tail)."""
        starts, t = [], 0.0
        for i, c in enumerate(self.video):
            if i > 0:
                t -= c.transition_duration
            starts.append(round(t, 4))
            t += c.duration
        return starts

    @property
    def duration(self) -> float:
        if not self.video:
            return 0.0
        return round(self.clip_starts()[-1] + self.video[-1].duration, 4)

    def asset(self, asset_id: str) -> AssetRef:
        return next(a for a in self.assets if a.id == asset_id)

    def content_hash(self) -> str:
        """Stable identity of an edit: same hash -> same render inputs."""
        canon = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()

    # ------------------------------------------------------------ validation
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
            if i == 0 and c.transition_in != "cut":
                c.transition_in, c.transition_duration = "cut", 0.0  # nothing to transition from
            if i > 0 and c.transition_duration >= min(c.duration, self.video[i - 1].duration) / 2:
                errors.append(f"video[{i}]: transition {c.transition_duration}s too long for adjacent clips")
        total = self.duration
        for kind, items in (("captions", self.captions), ("titles", self.titles)):
            for i, cap in enumerate(items):
                if cap.end <= cap.start:
                    errors.append(f"{kind}[{i}]: end must be > start")
                if cap.end > total + 1e-3:
                    errors.append(f"{kind}[{i}]: ends at {cap.end}s past timeline end {total:.2f}s")
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def render_problems(self) -> list[str]:
        """Constraints that only matter for a final render (an in-progress timeline may break them)."""
        p = []
        if not self.video:
            p.append("timeline has no clips")
        d = self.duration
        if self.video and not (self.output.min_duration - 0.05 <= d <= self.output.max_duration + 0.05):
            p.append(f"duration {d:.2f}s outside target {self.output.min_duration:.0f}-"
                     f"{self.output.max_duration:.0f}s")
        return p
