import pytest

from editing.operations import apply_action
from editing.timeline.schema import OutputSpec, Timeline
from perception.audio.loudness import measure_loudness
from rendering.ffmpeg.render import compile_timeline, render
from tests.fakes import synthetic_context


@pytest.fixture
def timeline(synthetic):
    ctx = synthetic_context(synthetic)
    t = Timeline(assets=ctx.assets, output=OutputSpec(min_duration=5, max_duration=20))
    for name, args in [("select_clip", {"scene_id": "S1", "src_in": 0, "src_out": 4}),
                       ("select_clip", {"scene_id": "S3"}),
                       ("select_clip", {"scene_id": "S4", "src_in": 8, "src_out": 10}),
                       ("add_transition", {"index": 1, "type": "fade", "duration": 0.5}),
                       ("generate_captions", {}), ("add_title", {"text": "Test"}),
                       ("apply_style", {"color": "warm"})]:
        r = apply_action(t, name, args, ctx)
        assert r.ok, r.error
        t = r.timeline
    return t


def test_compile_is_argv_only_and_deterministic(timeline):
    a, b = compile_timeline(timeline), compile_timeline(timeline)
    assert a.argv == b.argv and a.filtergraph == b.filtergraph and a.ass == b.ass
    assert a.argv[0] == "ffmpeg" and all(isinstance(x, str) for x in a.argv)
    assert "xfade=transition=fade" in a.filtergraph and "concat=n=2" in a.filtergraph
    assert "Dialogue:" in a.ass


def test_render_produces_valid_vertical_video(timeline, tmp_path):
    r = render(timeline, tmp_path)
    p = r.probe
    assert (p["width"], p["height"], p["aspect_ratio"]) == (1080, 1920, "9:16")
    assert p["has_audio"] and r.duration == pytest.approx(timeline.duration, abs=0.1)
    assert -15.5 < measure_loudness(r.path)["integrated_lufs"] < -12.5
    assert r.timeline_sha256 == timeline.content_hash()


def test_rejects_empty_timeline(synthetic):
    with pytest.raises(ValueError, match="no clips"):
        compile_timeline(Timeline(assets=synthetic_context(synthetic).assets))
