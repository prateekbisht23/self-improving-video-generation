"""Benchmark task format (PRD §8.1) and split-aware loading with holdout isolation (§8.2)."""

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
Category = Literal["instruction_following", "pacing_scene_selection", "reference_style",
                   "audio_captions", "personalization"]
Split = Literal["development", "validation", "holdout"]
SPLIT_DIRS: dict[str, Path] = {s: ROOT / s for s in ("development", "validation", "holdout")}


class HoldoutAccessError(PermissionError):
    """Raised when code that is not allowed to see the holdout split tries to load it."""


class HardConstraints(BaseModel):
    min_duration: float = 15
    max_duration: float = 30
    aspect_ratio: str = "9:16"
    captions_required: bool | None = None
    must_include: list[str] = Field(default_factory=list, description="spoken phrases that must be in the output")
    must_exclude: list[str] = Field(default_factory=list)


class BenchmarkTask(BaseModel):
    id: str
    version: int = 1
    category: Category
    split: Split
    sources: list[str] = Field(description="sample ids from samples/manifest.yaml")
    reference: str | None = Field(default=None, description="sample id of a style reference")
    instructions: str
    preferences: list[str] = Field(default_factory=list, description="creator preferences (personalization)")
    constraints: HardConstraints = HardConstraints()
    expected_checks: list[str] = Field(default_factory=list)
    human_annotations: dict | None = None

    @classmethod
    def load(cls, path: str | Path) -> "BenchmarkTask":
        t = cls.model_validate(yaml.safe_load(Path(path).read_text()))
        if SPLIT_DIRS[t.split] != Path(path).resolve().parent:
            raise ValueError(f"{path}: task says split={t.split} but lives in {Path(path).parent.name}/")
        return t


SCOPES = {"reference": lambda t: bool(t.reference)}  # see AgentConfig.scope


def in_scope(task: "BenchmarkTask", scope: str | None) -> bool:
    return scope is None or SCOPES[scope](task)


def load_tasks(splits: list[str] | str = ("development",), *, allow_holdout: bool = False) -> list[BenchmarkTask]:
    """Load tasks of the given splits. The holdout split needs an explicit opt-in, so the
    improvement loop (Phase 5) can't read it by accident."""
    splits = [splits] if isinstance(splits, str) else list(splits)
    if "holdout" in splits and not allow_holdout:
        raise HoldoutAccessError("holdout tasks are reserved for final assessment; pass allow_holdout=True "
                                 "only from the final-evaluation entry point")
    tasks = []
    for s in splits:
        tasks += [BenchmarkTask.load(p) for p in sorted(SPLIT_DIRS[s].glob("*.yaml"))]
    ids = [t.id for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task ids")
    return tasks


def dataset_version() -> str:
    """Content hash over ALL task files: any edit to any split changes the dataset version."""
    h = hashlib.sha256()
    for s in sorted(SPLIT_DIRS):
        for p in sorted(SPLIT_DIRS[s].glob("*.yaml")):
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return f"bench-v1-{h.hexdigest()[:10]}"
