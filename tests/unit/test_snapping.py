"""Cut snapping: edges land in word gaps / on sentence boundaries, as the evaluator defines them."""

from types import SimpleNamespace

import pytest

from editing.context import WordT
from editing.snapping import next_sentence_end, snap_clip
from evaluation.evaluators import temporal
from evaluation.inputs import EvalInput

WORDS = [WordT(0.0, 0.4, "Hello"), WordT(0.45, 0.9, "there."), WordT(1.0, 1.3, "This"), WordT(1.35, 1.6, "is"),
         WordT(1.65, 2.1, "a"), WordT(2.15, 2.8, "test."), WordT(3.5, 3.9, "After"), WordT(3.95, 4.5, "pause"),
         WordT(4.55, 5.0, "words"), WordT(5.05, 5.6, "continue"), WordT(5.65, 6.2, "here.")]


def checks(src_in, src_out):
    tl = {"video": [{"asset_id": "a", "src_in": src_in, "src_out": src_out}]}
    x = EvalInput(render_path="", instructions="", min_duration=0, max_duration=0, timeline=tl,
                  source_words={"a": [(w.start, w.end, w.text) for w in WORDS]})
    f = SimpleNamespace(readable=True, shots=[], silences=[], words=[], duration=src_out - src_in)
    return {r.id: r.passed for r in temporal.run(f, x)}


def test_baseline_edges_fail_the_evaluator():
    c = checks(1.4, 4.7)  # starts inside "is", ends inside "words"
    assert not c["temporal.cut_through_word"] and not c["temporal.dialogue_continuity"]


def test_word_mode_never_cuts_through_a_word():
    i, o = snap_clip(1.4, 4.7, WORDS, 0, 10, "word")
    assert checks(i, o)["temporal.cut_through_word"]
    assert abs(i - 1.4) < 0.3 and abs(o - 4.7) < 0.4


def test_sentence_mode_lands_on_sentence_boundaries():
    i, o = snap_clip(1.4, 4.7, WORDS, 0, 10, "sentence", max_shift=2.0)
    c = checks(i, o)
    assert c["temporal.cut_through_word"] and c["temporal.dialogue_continuity"]
    assert i == pytest.approx(0.95, abs=0.06)  # just before "This"


def test_sentence_mode_respects_max_shift_and_falls_back_to_word_gaps():
    i, o = snap_clip(4.0, 5.3, WORDS, 0, 10, "sentence", max_shift=0.3)  # no sentence boundary within 0.3s
    c = checks(i, o)
    assert c["temporal.cut_through_word"]
    assert abs(i - 4.0) < 0.3 and abs(o - 5.3) < 0.4


def test_scene_bounds_and_silence_are_respected():
    assert snap_clip(2.95, 3.3, WORDS, 2.9, 3.4, "sentence") == (2.95, 3.3)  # in a silent gap: unchanged
    i, o = snap_clip(1.4, 4.7, WORDS, 1.2, 4.9, "sentence")
    assert 1.2 <= i and o <= 4.9


def test_off_is_identity_and_next_sentence_end():
    assert snap_clip(1.4, 4.7, WORDS, 0, 10, "off") == (1.4, 4.7)
    assert next_sentence_end(1.0, WORDS, 10) == pytest.approx(2.9, abs=0.11)
