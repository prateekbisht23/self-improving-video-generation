"""Counterfactual replay: what WOULD a policy knob have done to the timelines we already have?

For knobs that act deterministically on clip edges (snap_cuts), we can apply them to the recorded
final timelines of the baseline's sessions and re-score with the evaluator's own deterministic
check functions. No rendering, no model calls, no quota. It is an estimate (in a real run the
agent would react to the changed durations), so it only informs the proposal; the experiment
decides.
"""

import uuid

from sqlalchemy import select

from db.models import EditingSession, Scene, TranscriptSegment
from editing.context import WordT
from editing.snapping import snap_clip

SETTINGS = [("off", None), ("word", None), ("sentence", 2.0), ("sentence", 5.0)]


def _words(s, asset_ids: list[str]) -> dict[str, list[tuple]]:
    out = {}
    for a in asset_ids:
        segs = s.scalars(select(TranscriptSegment).where(TranscriptSegment.asset_id == uuid.UUID(a))).all()
        out[a] = [(w["start"], w["end"], w["text"]) for g in segs for w in (g.words or [])]
    return out


def snap_replay(s, session_ids: list[str]) -> list[dict]:
    from types import SimpleNamespace

    from evaluation.evaluators import temporal
    from evaluation.inputs import EvalInput

    rows = []
    for mode, shift in SETTINGS:
        n = dc = cw = 0
        drift = 0.0
        for sid in session_ids:
            e = s.get(EditingSession, uuid.UUID(sid))
            if e is None or not e.versions:
                continue
            tl = e.versions[-1].timeline
            words = _words(s, e.source_asset_ids)
            video, before, after = [], 0.0, 0.0
            for c in tl.get("video", []):
                sc = s.scalar(select(Scene).where(Scene.asset_id == uuid.UUID(c["asset_id"]),
                                                  Scene.start <= c["src_in"] + 1e-3, Scene.end >= c["src_out"] - 1e-3))
                lo, hi = (sc.start, sc.end) if sc else (0.0, float("inf"))
                ws = [WordT(*w) for w in words.get(c["asset_id"], [])]
                i, o = snap_clip(c["src_in"], c["src_out"], ws, lo, hi, mode, shift or 2.0)
                video.append({**c, "src_in": i, "src_out": o})
                before += c["src_out"] - c["src_in"]
                after += o - i
            x = EvalInput(render_path="", instructions="", min_duration=0, max_duration=0,
                          timeline={**tl, "video": video}, source_words=words)
            f = SimpleNamespace(readable=True, shots=[], silences=[], words=[], duration=after)
            res = {r.id: r.passed for r in temporal.run(f, x)}
            n += 1
            dc += bool(res.get("temporal.dialogue_continuity"))
            cw += bool(res.get("temporal.cut_through_word"))
            drift += after - before
        if n:
            rows.append({"policy": {"snap_cuts": mode, **({"snap_max_shift": shift} if shift else {})},
                         "sessions": n, "dialogue_continuity_pass": round(dc / n, 2),
                         "cut_through_word_pass": round(cw / n, 2), "mean_duration_change_s": round(drift / n, 2)})
    return rows
