"""Everything an evaluation may look at. Deliberately excludes the agent's plan and reasoning."""

from pydantic import BaseModel, Field


class EvalInput(BaseModel):
    render_path: str
    instructions: str
    min_duration: float
    max_duration: float
    width: int = 1080
    height: int = 1920
    aspect_ratio: str = "9:16"
    loudness_target: float = -14.0
    captions_required: bool | None = None
    must_include: list[str] = Field(default_factory=list)   # spoken phrases / visual items
    must_exclude: list[str] = Field(default_factory=list)
    timeline: dict | None = None                            # the edit decision list (structure only)
    source_words: dict[str, list[tuple[float, float, str]]] = Field(default_factory=dict)  # asset -> words
    reference: dict | None = None                           # reference style profile, if any
