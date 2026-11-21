import pytest

from perception.scene_detection.detect import detect_scenes


def test_detects_known_cuts(synthetic):
    scenes = detect_scenes(synthetic / "cuts.mp4", duration=12.0)
    starts = [s.start for s in scenes]
    assert len(scenes) == 3
    assert starts[1] == pytest.approx(4.0, abs=0.1)
    assert starts[2] == pytest.approx(8.0, abs=0.1)
    assert all(0 <= s.start < s.end <= 12.0 for s in scenes)
