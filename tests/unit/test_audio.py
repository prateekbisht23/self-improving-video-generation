import pytest

from perception.audio.loudness import measure_loudness
from perception.audio.silence import detect_silence, parse_silencedetect

LOG = """[silencedetect @ 0x1] silence_start: 2.01
[silencedetect @ 0x1] silence_end: 4.99 | silence_duration: 2.98
[silencedetect @ 0x1] silence_start: 9.5
"""


def test_parse_silencedetect_handles_open_tail():
    r = parse_silencedetect(LOG, duration=10.0)
    assert [(s.start, s.end) for s in r] == [(2.01, 4.99), (9.5, 10.0)]


def test_detect_silence_fixture(synthetic):
    r = detect_silence(synthetic / "silence.mp4", duration=7.0)
    assert len(r) == 1
    assert r[0].start == pytest.approx(2.0, abs=0.1)
    assert r[0].end == pytest.approx(5.0, abs=0.1)


def test_loudness_is_measured(synthetic):
    lufs = measure_loudness(synthetic / "cuts.mp4")
    assert lufs["integrated_lufs"] is not None and -40 < lufs["integrated_lufs"] < 0
