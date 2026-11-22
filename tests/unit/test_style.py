import pytest

from perception.style import build_profile, color_stats, pace_of, shot_stats


def test_shot_stats_and_pace():
    s = shot_stats([(0, 1), (1, 3), (3, 4.5), (4.5, 10)], 10)
    assert (s.count, s.median, s.cuts_per_minute) == (4, 1.75, 18.0)
    assert pace_of(1.75) == "fast" and pace_of(3) == "medium" and pace_of(8) == "slow"


def test_color_stats(tmp_path):
    import cv2
    import numpy as np

    red, gray = tmp_path / "r.png", tmp_path / "g.png"
    cv2.imwrite(str(red), np.full((10, 10, 3), (40, 60, 200), np.uint8))   # BGR: warm
    cv2.imwrite(str(gray), np.full((10, 10, 3), 128, np.uint8))
    assert color_stats([str(red)]).warmth > 0.5
    assert color_stats([str(gray)]).suggested_preset == "bw"


def test_profile_without_model_gives_guidance(tmp_path):
    p = build_profile(duration=20, aspect_ratio="9:16", spans=[(0, 2), (2, 4), (4, 6), (6, 20)], frames=[],
                      words=[(0, 10, "x")] * 30, lufs=-14, silences=[(15, 17)], transcript_text="", use_model=False)
    assert p.pace == "fast" and p.guidance.target_shot_seconds == pytest.approx(2.0)
    assert p.silence_ratio == 0.1 and p.observed is None
