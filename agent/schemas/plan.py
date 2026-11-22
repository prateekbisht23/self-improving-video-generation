"""Structured output of the planner node (PRD FR-05)."""

from typing import Literal

from pydantic import BaseModel, Field

from editing.timeline.schema import ColorPreset, Position


class PlannedClip(BaseModel):
    scene_id: str = Field(description="scene id from the footage list, e.g. 'S4'")
    src_in: float = Field(description="start time in seconds; inside the scene, ideally where a sentence starts")
    src_out: float = Field(description="end time in seconds; inside the scene, ideally where a sentence ends")
    purpose: str = Field(description="why this clip, e.g. 'hook: launch is tomorrow'")


class EditPlan(BaseModel):
    understanding: str = Field(description="one sentence: what the creator wants")
    hook: str = Field(description="what the first 3 seconds show/say and why it grabs attention")
    clips: list[PlannedClip] = Field(description="clips in playback order")
    transition: Literal["cut", "fade", "dissolve"] = Field(description="transition between clips")
    captions: bool = Field(description="burn in word-synced captions of the speech")
    caption_position: Position
    title: str | None = Field(default=None, description="short on-screen title for the opening, or null")
    color: ColorPreset = Field(description="overall colour look")
    estimated_duration: float = Field(description="sum of clip durations in seconds")
