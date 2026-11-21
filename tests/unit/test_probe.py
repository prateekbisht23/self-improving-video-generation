import pytest

from perception.ffmpeg import FFmpegError
from perception.video.probe import probe


def test_probe_cuts(synthetic):
    m = probe(synthetic / "cuts.mp4")
    assert m.duration == pytest.approx(12.0, abs=0.1)
    assert (m.width, m.height, m.aspect_ratio) == (1280, 720, "16:9")
    assert m.fps == pytest.approx(30.0)
    assert m.has_audio and m.has_video


def test_probe_rejects_non_media(tmp_path):
    bad = tmp_path / "notes.mp4"
    bad.write_text("not a video")
    with pytest.raises(FFmpegError):
        probe(bad)
