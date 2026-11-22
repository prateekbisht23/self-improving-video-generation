import pytest

from editing.captions import build_captions
from editing.operations import apply_action
from editing.timeline.schema import OutputSpec, Timeline
from tests.fakes import synthetic_context


@pytest.fixture
def ctx(synthetic):
    return synthetic_context(synthetic)


@pytest.fixture
def tl(ctx):
    t = Timeline(assets=ctx.assets, output=OutputSpec(min_duration=5, max_duration=20))
    for sid in ("S1", "S2", "S3"):
        t = apply_action(t, "select_clip", {"scene_id": sid}, ctx).timeline
    return t


def test_select_defaults_to_scene_and_records_provenance(tl):
    assert [(c.scene_id, c.src_in, c.src_out) for c in tl.video] == [("S1", 0, 9.9), ("S2", 0, 4), ("S3", 4, 8)]
    assert tl.duration == pytest.approx(17.9)


@pytest.mark.parametrize("name, args, err", [
    ("select_clip", {"scene_id": "S99"}, "unknown scene"),
    ("select_clip", {"scene_id": "S2", "src_in": 1, "src_out": 1.2}, "minimum is 0.5s"),
    ("select_clip", {"scene_id": "S4", "src_in": 9, "src_out": 13}, "past the end"),
    ("trim_clip", {"index": 7}, "no clip at index 7"),
    ("reorder_clips", {"order": [0, 0, 1]}, "permutation"),
    ("add_transition", {"index": 0, "type": "fade"}, "invalid arguments"),
    ("explode", {}, "unknown operation"),
])
def test_invalid_actions_leave_timeline_unchanged(tl, ctx, name, args, err):
    before = tl.content_hash()
    r = apply_action(tl, name, args, ctx)
    assert not r.ok and err in r.error and r.timeline is None
    assert tl.content_hash() == before  # never mutated


def test_ops_are_pure_and_versionable(tl, ctx):
    r = apply_action(tl, "reorder_clips", {"order": [2, 0, 1]}, ctx)
    assert r.ok and [c.scene_id for c in r.timeline.video] == ["S3", "S1", "S2"]
    assert [c.scene_id for c in tl.video] == ["S1", "S2", "S3"]
    assert r.timeline.content_hash() != tl.content_hash()


def test_transition_overlaps_clips(tl, ctx):
    r = apply_action(tl, "add_transition", {"index": 1, "type": "dissolve", "duration": 0.5}, ctx)
    assert r.timeline.duration == pytest.approx(17.4)
    assert r.timeline.clip_starts() == pytest.approx([0, 9.4, 13.4])


def test_generated_captions_follow_clips_and_regenerate(tl, ctx):
    r = apply_action(tl, "generate_captions", {"max_words": 3}, ctx)
    texts = [c.text for c in r.timeline.captions]
    assert texts[:2] == ["Welcome to the", "editing lab."]           # punctuation ends a card
    assert "Every word six-year" in texts                            # hyphen token glued, not a new word
    moved = apply_action(r.timeline, "reorder_clips", {"order": [1, 0, 2]}, ctx).timeline
    assert moved.captions[0].start == pytest.approx(4.0)  # speech now starts after the 4s clip


def test_captions_never_span_a_cut(ctx):
    t = Timeline(assets=ctx.assets)
    t = apply_action(t, "select_clip", {"scene_id": "S1", "src_in": 0, "src_out": 2.5}, ctx).timeline
    t = apply_action(t, "select_clip", {"scene_id": "S1", "src_in": 2.5, "src_out": 4}, ctx).timeline
    caps = build_captions(t, ctx)
    boundary = t.clip_starts()[1]
    assert all(c.end <= boundary + 0.2 or c.start >= boundary - 1e-6 for c in caps)


def test_style_and_titles(tl, ctx):
    r = apply_action(tl, "apply_style", {"color": "bw", "caption_position": "top", "caption_uppercase": True}, ctx)
    r = apply_action(r.timeline, "add_title", {"text": "Lab day", "end": 99}, ctx)
    assert r.timeline.style.color == "bw" and r.timeline.style.captions.position == "top"
    assert r.timeline.titles[0].end == pytest.approx(r.timeline.duration)  # clamped


def test_search_is_read_only(tl, ctx):
    r = apply_action(tl, "search_scenes", {"query": "fractal"}, ctx)
    assert r.ok and r.timeline is None and r.data[0]["scene_id"] == "S4"


def test_transition_longer_than_half_a_short_clip_is_rejected(tl, ctx):
    short = apply_action(tl, "trim_clip", {"index": 1, "src_out": 2.0}, ctx).timeline  # 2s clip
    r = apply_action(short, "add_transition", {"index": 1, "type": "fade", "duration": 1.5}, ctx)
    assert not r.ok and "too long" in r.error
