"""Reference-video style profiles (PRD FR-04).

measured  (deterministic, reproducible): shot-length distribution, pace, speech rate,
          loudness, silence, colour statistics
observed  (one vision-model call over a contact sheet + transcript excerpt): caption look,
          transitions, framing, narrative structure — labelled as model observations

`guidance` turns the profile into concrete editing defaults the planner and compiler use.
"""

import base64
import statistics
from typing import Literal

import cv2
import numpy as np
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from config.models import get_chat_model, model_id

EXTRACTOR_VERSION = "style-1.0"


class ShotStats(BaseModel):
    count: int
    mean: float
    median: float
    p10: float
    p90: float
    cuts_per_minute: float
    durations: list[float]


class ColorStats(BaseModel):
    brightness: float = Field(description="mean V channel, 0-1")
    saturation: float = Field(description="mean S channel, 0-1")
    warmth: float = Field(description="mean(R) - mean(B), -1..1")
    suggested_preset: str


class StyleObservation(BaseModel):
    """What a vision model reports from a contact sheet of the reference video."""

    captions_present: bool = Field(description="burned-in subtitles/captions of speech are visible")
    caption_position: Literal["top", "center", "bottom", "none"]
    caption_uppercase: bool = Field(description="captions are written in ALL CAPS")
    caption_notes: str = Field(description="font weight, colour, background box, words per card")
    on_screen_text: str = Field(description="other text: titles, labels, lower thirds")
    transitions: list[str] = Field(description="e.g. hard cuts, crossfades, zooms, wipes")
    framing: str = Field(description="shot types/composition, e.g. talking head medium shot, b-roll wides")
    narrative_structure: list[str] = Field(description="3-6 beats in order, e.g. hook, context, payoff, CTA")


class Guidance(BaseModel):
    target_shot_seconds: float
    max_shot_seconds: float
    caption_position: Literal["top", "center", "bottom"]
    caption_uppercase: bool
    color: str
    transition: Literal["cut", "fade", "dissolve"]
    pace: Literal["fast", "medium", "slow"]


class StyleProfileData(BaseModel):
    version: str = EXTRACTOR_VERSION
    duration: float
    aspect_ratio: str | None
    shots: ShotStats
    pace: Literal["fast", "medium", "slow"]
    words_per_minute: float | None
    speech_coverage: float
    loudness_lufs: float | None
    silence_ratio: float
    color: ColorStats
    observed: StyleObservation | None = None
    observed_by: str | None = None
    evidence_frames: list[float] = Field(default_factory=list, description="timestamps shown to the model")
    guidance: Guidance


def shot_stats(spans: list[tuple[float, float]], duration: float) -> ShotStats:
    d = sorted(round(e - s, 3) for s, e in spans)
    q = np.percentile(d, [10, 90]) if d else [0, 0]
    return ShotStats(count=len(d), mean=round(statistics.fmean(d), 2), median=round(statistics.median(d), 2),
                     p10=round(float(q[0]), 2), p90=round(float(q[1]), 2),
                     cuts_per_minute=round(max(len(d) - 1, 0) / (duration / 60), 2),
                     durations=[round(e - s, 2) for s, e in spans])


def pace_of(median_shot: float) -> Literal["fast", "medium", "slow"]:
    return "fast" if median_shot < 2.5 else "medium" if median_shot < 5 else "slow"


def color_stats(frame_paths: list[str]) -> ColorStats:
    b, s, w = [], [], []
    for p in frame_paths:
        img = cv2.imread(p)
        if img is None:
            continue
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32) / 255
        b.append(hsv[..., 2].mean())
        s.append(hsv[..., 1].mean())
        f = img.astype(np.float32) / 255
        w.append(f[..., 2].mean() - f[..., 0].mean())  # BGR: R - B
    if not b:
        return ColorStats(brightness=0, saturation=0, warmth=0, suggested_preset="none")
    bright, sat, warm = (round(float(np.mean(x)), 3) for x in (b, s, w))
    preset = ("bw" if sat < 0.06 else "muted" if sat < 0.18 else "vivid" if sat > 0.5
              else "warm" if warm > 0.06 else "cool" if warm < -0.06 else "none")
    return ColorStats(brightness=bright, saturation=sat, warmth=warm, suggested_preset=preset)


def contact_sheet(frames: list[tuple[float, str]], cols: int = 4, width: int = 320) -> bytes:
    tiles = []
    for t, p in frames:
        img = cv2.imread(p)
        if img is None:
            continue
        h = int(img.shape[0] * width / img.shape[1])
        img = cv2.resize(img, (width, h))
        cv2.putText(img, f"{t:.1f}s", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        tiles.append(img)
    h = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in tiles]
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    ok, buf = cv2.imencode(".jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes()


OBSERVE_SYSTEM = (
    "You analyse the editing style of a reference video for a video editor. You get a contact sheet "
    "of frames (timestamps in yellow) and a transcript excerpt. Report only what is visible or said; "
    "say 'none' / empty when something is absent."
)


def observe(sheet_jpg: bytes, transcript_excerpt: str) -> StyleObservation:
    b64 = base64.b64encode(sheet_jpg).decode()
    model = get_chat_model("vision").with_structured_output(StyleObservation)
    return model.invoke([
        SystemMessage(OBSERVE_SYSTEM),
        HumanMessage(content=[
            {"type": "text", "text": f"Transcript excerpt:\n{transcript_excerpt[:1500] or '(no speech)'}"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]),
    ])


def derive_guidance(shots: ShotStats, pace: str, color: ColorStats, obs: StyleObservation | None) -> Guidance:
    target = min(max(shots.median, 1.2), 6.0)
    transition = "cut"
    if obs and any(k in " ".join(obs.transitions).lower() for k in ("fade", "dissolve", "crossfade")):
        transition = "fade"
    return Guidance(
        target_shot_seconds=round(target, 2), max_shot_seconds=round(min(max(shots.p90, target * 1.5), 10.0), 2),
        caption_position=(obs.caption_position if obs and obs.caption_position != "none" else "bottom"),
        caption_uppercase=bool(obs and obs.caption_uppercase), color=color.suggested_preset,
        transition=transition, pace=pace)


def build_profile(*, duration: float, aspect_ratio: str | None, spans: list[tuple[float, float]],
                  frames: list[tuple[float, str]], words: list[tuple[float, float, str]],
                  lufs: float | None, silences: list[tuple[float, float]], transcript_text: str,
                  use_model: bool = True) -> StyleProfileData:
    shots = shot_stats(spans, duration)
    pace = pace_of(shots.median)
    spoken = sum(e - s for s, e, _ in words)
    wpm = round(len(words) / (spoken / 60), 1) if spoken > 5 else None
    color = color_stats([p for _, p in frames])
    sample = frames if len(frames) <= 12 else [frames[round(i * (len(frames) - 1) / 11)] for i in range(12)]
    obs = observe(contact_sheet(sample), transcript_text) if use_model and sample else None
    return StyleProfileData(
        duration=duration, aspect_ratio=aspect_ratio, shots=shots, pace=pace, words_per_minute=wpm,
        speech_coverage=round(spoken / duration, 3) if duration else 0, loudness_lufs=lufs,
        silence_ratio=round(sum(e - s for s, e in silences) / duration, 3) if duration else 0,
        color=color, observed=obs, observed_by=model_id("vision") if obs else None,
        evidence_frames=[t for t, _ in sample], guidance=derive_guidance(shots, pace, color, obs))
