import pytest
from pydantic import ValidationError

from editing.timeline.schema import AssetRef, Caption, Timeline, VideoClip

ASSET = AssetRef(id="a1", path="x.mp4", duration=10.0)


def test_valid_timeline_duration():
    tl = Timeline(assets=[ASSET], video=[
        VideoClip(asset_id="a1", src_in=0, src_out=4),
        VideoClip(asset_id="a1", src_in=6, src_out=9, transition_in="fade", transition_duration=0.5),
    ])
    assert tl.duration == pytest.approx(6.5)
    assert tl.output.aspect_ratio == "9:16"


@pytest.mark.parametrize("clip, msg", [
    (dict(asset_id="a1", src_in=8, src_out=12), "beyond asset duration"),
    (dict(asset_id="nope", src_in=0, src_out=2), "unknown asset"),
    (dict(asset_id="a1", src_in=5, src_out=3), "must be >"),
])
def test_invalid_clips_rejected(clip, msg):
    with pytest.raises(ValidationError, match=msg):
        Timeline(assets=[ASSET], video=[VideoClip(**clip)])


def test_caption_past_end_rejected():
    with pytest.raises(ValidationError, match="past timeline end"):
        Timeline(assets=[ASSET], video=[VideoClip(asset_id="a1", src_in=0, src_out=3)],
                 captions=[Caption(start=2, end=5, text="hi")])
