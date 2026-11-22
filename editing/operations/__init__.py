"""Typed editing operations (PRD FR-06).

Every operation:
- has a Pydantic input schema (validated before anything happens),
- is a pure function  (timeline, args, ctx) -> new timeline  that never mutates its input,
- is re-validated as a whole Timeline afterwards, so an operation can't produce an invalid edit,
- returns a structured ActionResult with an actionable error on failure.

The same registry backs the agent (planned actions + LLM tool calls) and the user-facing API.
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from editing.captions import build_captions
from editing.context import EditContext
from editing.timeline.schema import (
    Caption,
    ColorPreset,
    Position,
    Timeline,
    Title,
    Transition,
    VideoClip,
)


class OperationError(ValueError):
    """An operation was understood but can't be applied (bad index, out-of-range time...)."""


class ActionResult(BaseModel):
    ok: bool
    name: str
    args: dict
    message: str = ""
    error: str | None = None
    data: Any = None
    timeline: Timeline | None = None  # new timeline when ok and the op changes it

    @property
    def changed(self) -> bool:
        return self.ok and self.timeline is not None


# ------------------------------------------------------------------ input schemas
class SearchScenes(BaseModel):
    """Find scenes matching a description (visual content or spoken words)."""
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=20)


class SelectClip(BaseModel):
    """Add footage from a scene to the edit. Defaults to the whole scene; src_in/src_out trim it."""
    scene_id: str = Field(description="scene id like 'S4'")
    src_in: float | None = Field(default=None, ge=0, description="source start (s); default scene start")
    src_out: float | None = Field(default=None, gt=0, description="source end (s); default scene end")
    position: int | None = Field(default=None, ge=0, description="insert index; default append")
    purpose: str | None = Field(default=None, max_length=200)


class TrimClip(BaseModel):
    """Change the source in/out points of clip `index`."""
    index: int = Field(ge=0)
    src_in: float | None = Field(default=None, ge=0)
    src_out: float | None = Field(default=None, gt=0)


class RemoveClip(BaseModel):
    """Delete clip `index` from the edit."""
    index: int = Field(ge=0)


class ReorderClips(BaseModel):
    """Reorder clips; `order` is a permutation of current indices, e.g. [2, 0, 1]."""
    order: list[int]


class AddTransition(BaseModel):
    """Set the transition INTO clip `index` (index >= 1)."""
    index: int = Field(ge=1)
    type: Transition = "fade"
    duration: float = Field(default=0.4, ge=0, le=1.5)


class AdjustAudio(BaseModel):
    """Set the volume of one clip (index) or all clips (index omitted). 1.0 = unchanged."""
    volume: float = Field(ge=0, le=4)
    index: int | None = Field(default=None, ge=0)


class SetFraming(BaseModel):
    """Move the 9:16 crop window: 0 = left edge, 0.5 = centre, 1 = right edge of the source."""
    index: int = Field(ge=0)
    crop_x: float = Field(ge=0, le=1)


class AddCaption(BaseModel):
    """Add a manual caption in timeline time (turns off automatic transcript captions)."""
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=200)


class GenerateCaptions(BaseModel):
    """Create word-synced captions from the transcript of the selected clips."""
    max_words: int | None = Field(default=None, ge=1, le=12)


class AddTitle(BaseModel):
    """Add a title card overlay (top of frame) in timeline time."""
    text: str = Field(min_length=1, max_length=80)
    start: float = Field(default=0.0, ge=0)
    end: float = Field(default=2.5, gt=0)


class ApplyStyle(BaseModel):
    """Set the visual look and caption appearance."""
    color: ColorPreset | None = None
    caption_position: Position | None = None
    caption_size: int | None = Field(default=None, ge=20, le=160)
    caption_uppercase: bool | None = None
    caption_highlight: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f]{6}$")


# ------------------------------------------------------------------ implementations
def _copy(tl: Timeline) -> Timeline:
    return tl.model_copy(deep=True)


def _clip(tl: Timeline, index: int) -> VideoClip:
    if not 0 <= index < len(tl.video):
        raise OperationError(f"no clip at index {index}; timeline has {len(tl.video)} clips (0-{len(tl.video)-1})")
    return tl.video[index]


def _after_clip_change(tl: Timeline, ctx: EditContext) -> Timeline:
    """Keep derived tracks consistent when clips move: regenerate transcript captions,
    drop/clamp overlays that now fall past the end."""
    if tl.captions_source == "transcript":
        tl.captions = build_captions(tl, ctx)
    total = tl.duration
    tl.captions = [c for c in tl.captions if c.start < total]
    for c in tl.captions:
        c.end = min(c.end, total)
    tl.titles = [t for t in tl.titles if t.start < total]
    for t in tl.titles:
        t.end = min(t.end, total)
    if tl.video:
        tl.video[0].transition_in, tl.video[0].transition_duration = "cut", 0.0
    return tl


def op_search_scenes(tl, a: SearchScenes, ctx: EditContext):
    if ctx.search is None:
        raise OperationError("scene search is not available in this context")
    hits = ctx.search(a.query, a.k)
    return None, [{"scene_id": h.sid, "start": h.start, "end": h.end, "description": h.description,
                   "transcript": h.transcript[:200]} for h in hits]


def op_select_clip(tl, a: SelectClip, ctx: EditContext):
    sc = ctx.scene(a.scene_id)
    src_in = sc.start if a.src_in is None else a.src_in
    src_out = sc.end if a.src_out is None else a.src_out
    asset = next(x for x in ctx.assets if x.id == sc.asset_id)
    if src_out > asset.duration + 1e-3:
        raise OperationError(f"src_out {src_out}s is past the end of the source ({asset.duration}s)")
    if src_out - src_in < 0.5:
        raise OperationError(f"clip would be {src_out - src_in:.2f}s; minimum is 0.5s")
    new = _copy(tl)
    clip = VideoClip(asset_id=sc.asset_id, src_in=round(src_in, 3), src_out=round(src_out, 3),
                     scene_id=sc.sid, purpose=a.purpose)
    pos = len(new.video) if a.position is None else min(a.position, len(new.video))
    new.video.insert(pos, clip)
    return _after_clip_change(new, ctx), {"index": pos, "duration": round(clip.duration, 3)}


def op_trim_clip(tl, a: TrimClip, ctx):
    new = _copy(tl)
    c = _clip(new, a.index)
    src_in = c.src_in if a.src_in is None else a.src_in
    src_out = c.src_out if a.src_out is None else a.src_out
    if src_out - src_in < 0.5:
        raise OperationError(f"trimmed clip would be {src_out - src_in:.2f}s; minimum is 0.5s")
    new.video[a.index] = c.model_copy(update={"src_in": round(src_in, 3), "src_out": round(src_out, 3)})
    return _after_clip_change(new, ctx), {"duration": round(src_out - src_in, 3)}


def op_remove_clip(tl, a: RemoveClip, ctx):
    new = _copy(tl)
    _clip(new, a.index)
    new.video.pop(a.index)
    return _after_clip_change(new, ctx), None


def op_reorder_clips(tl, a: ReorderClips, ctx):
    if sorted(a.order) != list(range(len(tl.video))):
        raise OperationError(f"order must be a permutation of 0..{len(tl.video)-1}, got {a.order}")
    new = _copy(tl)
    new.video = [new.video[i] for i in a.order]
    return _after_clip_change(new, ctx), None


def op_add_transition(tl, a: AddTransition, ctx):
    new = _copy(tl)
    c = _clip(new, a.index)
    dur = 0.0 if a.type == "cut" else (a.duration or 0.4)
    new.video[a.index] = c.model_copy(update={"transition_in": a.type, "transition_duration": dur})
    return _after_clip_change(new, ctx), None


def op_adjust_audio(tl, a: AdjustAudio, ctx):
    new = _copy(tl)
    targets = [a.index] if a.index is not None else range(len(new.video))
    for i in targets:
        _clip(new, i).volume = a.volume
    return new, None


def op_set_framing(tl, a: SetFraming, ctx):
    new = _copy(tl)
    _clip(new, a.index).crop_x = a.crop_x
    return new, None


def op_add_caption(tl, a: AddCaption, ctx):
    new = _copy(tl)
    if new.captions_source == "transcript":
        new.captions = []
    new.captions_source = "manual"
    new.captions.append(Caption(start=a.start, end=a.end, text=a.text))
    new.captions.sort(key=lambda c: c.start)
    return new, None


def op_generate_captions(tl, a: GenerateCaptions, ctx):
    if not tl.video:
        raise OperationError("add clips before generating captions")
    new = _copy(tl)
    if a.max_words:
        new.style.captions.max_words = a.max_words
    new.captions_source = "transcript"
    new.captions = build_captions(new, ctx)
    if not new.captions:
        raise OperationError("selected clips contain no transcribed speech to caption")
    return new, {"captions": len(new.captions)}


def op_add_title(tl, a: AddTitle, ctx):
    new = _copy(tl)
    end = min(a.end, new.duration) if new.video else a.end
    new.titles.append(Title(text=a.text, start=a.start, end=end))
    return new, None


def op_apply_style(tl, a: ApplyStyle, ctx):
    new = _copy(tl)
    if a.color is not None:
        new.style.color = a.color
    cs = new.style.captions
    for field, value in (("position", a.caption_position), ("size", a.caption_size),
                         ("uppercase", a.caption_uppercase), ("highlight", a.caption_highlight)):
        if value is not None:
            setattr(cs, field, value)
    return new, None


OPERATIONS: dict[str, tuple[type[BaseModel], Callable]] = {
    "search_scenes": (SearchScenes, op_search_scenes),
    "select_clip": (SelectClip, op_select_clip),
    "trim_clip": (TrimClip, op_trim_clip),
    "remove_clip": (RemoveClip, op_remove_clip),
    "reorder_clips": (ReorderClips, op_reorder_clips),
    "add_transition": (AddTransition, op_add_transition),
    "adjust_audio": (AdjustAudio, op_adjust_audio),
    "set_framing": (SetFraming, op_set_framing),
    "add_caption": (AddCaption, op_add_caption),
    "generate_captions": (GenerateCaptions, op_generate_captions),
    "add_title": (AddTitle, op_add_title),
    "apply_style": (ApplyStyle, op_apply_style),
}
READ_ONLY = {"search_scenes"}


def apply_action(tl: Timeline, name: str, args: dict, ctx: EditContext) -> ActionResult:
    """Validate + execute one operation. On any failure the input timeline is untouched."""
    if name not in OPERATIONS:
        return ActionResult(ok=False, name=name, args=args,
                            error=f"unknown operation '{name}'; valid: {', '.join(OPERATIONS)}")
    schema, fn = OPERATIONS[name]
    try:
        parsed = schema.model_validate(args)
    except ValidationError as e:
        return ActionResult(ok=False, name=name, args=args, error=f"invalid arguments: {_short(e)}")
    try:
        new_tl, data = fn(tl, parsed, ctx)
        if new_tl is not None:  # whole-timeline invariants (asset bounds, overlays, transitions)
            new_tl = Timeline.model_validate(new_tl.model_dump())
    except (OperationError, KeyError) as e:
        return ActionResult(ok=False, name=name, args=args, error=str(e).strip("'\""))
    except ValidationError as e:
        return ActionResult(ok=False, name=name, args=args, error=f"would make the timeline invalid: {_short(e)}")
    return ActionResult(ok=True, name=name, args=parsed.model_dump(exclude_none=True), data=data,
                        timeline=new_tl, message=f"{name} ok")


def _short(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, x['loc'])) or 'timeline'}: {x['msg']}" for x in e.errors()[:5])
