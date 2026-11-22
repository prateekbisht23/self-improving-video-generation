"""What editing operations may read: analysed scenes, word timings, a search function.

Scenes get short ids (S1, S2, ...) because LLMs copy short ids far more reliably than UUIDs.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from editing.timeline.schema import AssetRef


@dataclass
class SceneInfo:
    sid: str            # short id shown to the model, e.g. "S4"
    db_id: str          # scenes.id
    asset_id: str
    index: int
    start: float
    end: float
    description: str = ""
    tags: list[str] = field(default_factory=list)
    transcript: str = ""
    speech_ratio: float = 0.0
    segments: list[tuple[float, float, str]] = field(default_factory=list)  # (start, end, text) source time

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class WordT:
    start: float
    end: float
    text: str
    clip: int = -1  # index of the timeline clip the word ended up in (set by caption mapping)


@dataclass
class EditContext:
    assets: list[AssetRef]
    scenes: dict[str, SceneInfo]                       # by short id
    words: dict[str, list[WordT]] = field(default_factory=dict)   # asset_id -> words (source time)
    search: Callable[[str, int], list[SceneInfo]] | None = None

    def scene(self, sid: str) -> SceneInfo:
        sc = self.scenes.get(sid.strip().upper())
        if sc is None:
            raise KeyError(f"unknown scene '{sid}'; valid ids: {', '.join(list(self.scenes)[:40])}")
        return sc
