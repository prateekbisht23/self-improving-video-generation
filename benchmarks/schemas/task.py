"""Benchmark task format (PRD §8.1)."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Category = Literal["instruction_following", "pacing_scene_selection", "reference_style",
                   "audio_captions", "personalization"]
Split = Literal["development", "validation", "holdout"]


class HardConstraints(BaseModel):
    min_duration: float | None = None
    max_duration: float | None = None
    aspect_ratio: str | None = "9:16"
    captions_required: bool = False
    must_include: list[str] = Field(default_factory=list,
                                    description="content that must appear (spoken phrase or visual)")
    must_exclude: list[str] = Field(default_factory=list)


class BenchmarkTask(BaseModel):
    id: str
    version: int = 1
    category: Category
    split: Split
    sources: list[str]
    reference: str | None = None
    instructions: str
    creator_id: str | None = None
    constraints: HardConstraints = HardConstraints()
    expected_checks: list[str] = Field(default_factory=list)
    human_annotations: dict | None = None

    @classmethod
    def load(cls, path: str | Path) -> "BenchmarkTask":
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))
