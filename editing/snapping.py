"""Move clip edges to speech boundaries (policy knob `snap_cuts`).

A cut point is "safe" when it sits in a gap between words (never inside one). It is a
"sentence boundary" when, in addition, the word before it ends a sentence (. ? !) or there is a
pause of >= PAUSE seconds. These are the same definitions the evaluator uses for
temporal.cut_through_word and temporal.dialogue_continuity, so the policy targets exactly what is measured.

Pure functions over source-time word lists; no I/O.
"""

from collections.abc import Sequence

SENTENCE_END = (".", "?", "!")
PAUSE = 0.35   # a gap this long counts as a sentence boundary
PAD = 0.1      # how far outside the word we cut, when the gap allows it
MIN_CLIP = 0.8
MAX_SHIFT = 2.0  # sentence mode: an edge moves at most this far, else falls back to the nearest word gap


def _boundaries(words: Sequence, sentence: bool) -> tuple[list[float], list[float]]:
    """Candidate in-points (just before a word) and out-points (just after a word)."""
    ins, outs = [], []
    n = len(words)
    for i, w in enumerate(words):
        prev = words[i - 1] if i else None
        nxt = words[i + 1] if i + 1 < n else None
        starts_sentence = prev is None or prev.text.rstrip().endswith(SENTENCE_END) or w.start - prev.end >= PAUSE
        ends_sentence = nxt is None or w.text.rstrip().endswith(SENTENCE_END) or nxt.start - w.end >= PAUSE
        if starts_sentence or not sentence:
            lo = prev.end if prev else w.start - PAD
            ins.append(max(w.start - PAD, (lo + w.start) / 2) if lo < w.start else w.start)
        if ends_sentence or not sentence:
            hi = nxt.start if nxt else w.end + PAD
            outs.append(min(w.end + PAD, (w.end + hi) / 2) if hi > w.end else w.end)
    return ins, outs


def snap_clip(src_in: float, src_out: float, words: Sequence, lo: float, hi: float,
              mode: str = "sentence", max_shift: float = MAX_SHIFT) -> tuple[float, float]:
    """Return (new_in, new_out) within [lo, hi] (the scene bounds).

    - 'sentence': nearest sentence start / sentence end within `max_shift` seconds; falls back to
      'word' for an edge with no such boundary (keeps the edit's duration close to the plan).
    Boundaries are computed over ALL words (a scene that begins mid-sentence does not start a
    sentence), then restricted to the scene.
    - 'word': nearest gap between words.
    Edges in silence (no word within reach) and clips that would collapse are left unchanged.
    """
    if mode == "off":
        return src_in, src_out
    words = sorted(words, key=lambda w: w.start)
    inside = [w for w in words if w.end > lo and w.start < hi]
    if not inside:
        return src_in, src_out

    def pick(points: list[float], t: float, lo_: float, hi_: float, reach: float) -> float | None:
        ok = [p for p in points if lo_ <= p <= hi_ and abs(p - t) <= reach]
        return min(ok, key=lambda p: abs(p - t)) if ok else None

    def in_speech(t: float) -> bool:  # an edge inside a word or a short gap needs snapping
        return any(w.start - PAUSE < t < w.end + PAUSE for w in inside)

    new_in, new_out = src_in, src_out
    for m in ([mode, "word"] if mode == "sentence" else ["word"]):
        ins, outs = _boundaries(words, sentence=(m == "sentence"))
        # padding may reach just outside the scene: clamp instead of discarding the boundary
        ins = [lo if lo - PAD <= p < lo else p for p in ins]
        outs = [hi if hi < p <= hi + PAD else p for p in outs]
        reach = max_shift if m == "sentence" else 1.0
        if new_in == src_in and in_speech(src_in):
            p = pick(ins, src_in, lo, src_out - MIN_CLIP, reach)
            new_in = round(p, 3) if p is not None else new_in
        if new_out == src_out and in_speech(src_out):
            p = pick(outs, src_out, max(new_in, src_in) + MIN_CLIP, hi, reach)
            new_out = round(p, 3) if p is not None else new_out
    if new_out - new_in < MIN_CLIP:
        return src_in, src_out
    return new_in, new_out


def next_sentence_end(t: float, words: Sequence, hi: float) -> float | None:
    """First sentence-end out-point after t (for extending a clip without cutting mid-sentence)."""
    _, outs = _boundaries([w for w in words if w.start < hi], sentence=True)
    later = [p for p in outs if t + 0.2 < p <= hi]
    return min(later) if later else None
