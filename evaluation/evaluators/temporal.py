"""Temporal checks: pacing, repetition, dead air, and cuts that break speech."""

import re
import statistics

from evaluation.features import RenderFeatures
from evaluation.inputs import EvalInput
from evaluation.schemas import CheckResult, Evidence

SENTENCE_END = (".", "?", "!")


def _c(id_, passed, severity, message, kind="deterministic", category="temporal", **kw) -> CheckResult:
    return CheckResult(id=f"{category}.{id_}", category=category, kind=kind, passed=passed,
                       severity=severity, message=message, **kw)


def clip_starts(tl: dict) -> list[float]:
    starts, t = [], 0.0
    for i, c in enumerate(tl["video"]):
        if i > 0:
            t -= c.get("transition_duration", 0) or 0
        starts.append(t)
        t += c["src_out"] - c["src_in"]
    return starts


def run(f: RenderFeatures, x: EvalInput) -> list[CheckResult]:
    out: list[CheckResult] = []
    if not f.readable:
        return out

    # shot lengths measured on the render itself
    shots = [s.end - s.start for s in f.shots] or [f.duration]
    max_shot = (x.reference or {}).get("guidance", {}).get("max_shot_seconds") or 12.0
    long_shots = [s for s in f.shots if s.end - s.start > max_shot + 0.5]
    out.append(_c("shot_durations", not long_shots, "minor",
                  f"{len(shots)} shots, median {statistics.median(shots):.1f}s; "
                  f"{len(long_shots)} longer than {max_shot:.1f}s",
                  measurements={"count": len(shots), "median": round(statistics.median(shots), 2),
                                "max": round(max(shots), 2), "limit": max_shot},
                  evidence=[Evidence(start=s.start, end=s.end, detail="long shot") for s in long_shots]))

    # dead air in the output (ignores the first/last 0.3s)
    gaps = [s for s in f.silences if s.end - s.start >= 1.0 and s.start > 0.3 and s.end < f.duration - 0.3]
    speechy = len(f.words) > 5
    out.append(_c("dead_air", (not gaps) if speechy else None, "major" if any(g.end - g.start > 2 for g in gaps)
                  else "minor", f"{len(gaps)} silent gap(s) >= 1s" if gaps else "no long silences",
                  evidence=[Evidence(start=g.start, end=g.end, detail="silence") for g in gaps]))

    tl = x.timeline
    if not tl or not tl.get("video"):
        return out

    # repeated footage: two clips covering the same source range
    rep = []
    clips = tl["video"]
    starts = clip_starts(tl)
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            a, b = clips[i], clips[j]
            if a["asset_id"] == b["asset_id"]:
                ov = min(a["src_out"], b["src_out"]) - max(a["src_in"], b["src_in"])
                if ov > 0.5:
                    rep.append(Evidence(start=starts[j], end=starts[j] + (b["src_out"] - b["src_in"]),
                                        detail=f"clip {j} repeats {ov:.1f}s of clip {i}"))
    out.append(_c("repeated_footage", not rep, "major",
                  f"{len(rep)} repeated segment(s)" if rep else "no repeated footage", evidence=rep))

    # cuts vs speech: through a word, or starting/ending mid-sentence (source word timings)
    through, mid_start, mid_end = [], [], []
    for i, c in enumerate(clips):
        words = sorted(x.source_words.get(c["asset_id"], []))
        if not words:
            continue
        t0 = starts[i]
        dur = c["src_out"] - c["src_in"]
        for edge, src_t, t_tl in (("in", c["src_in"], t0), ("out", c["src_out"], t0 + dur)):
            for ws, we, wt in words:
                if ws + 0.06 < src_t < we - 0.06:
                    through.append(Evidence(start=t_tl, end=t_tl, detail=f"clip {i} {edge}-point cuts '{wt}'"))
        before = [w for w in words if w[1] <= c["src_in"] + 0.06]
        first_in = next((w for w in words if w[0] >= c["src_in"] - 0.06), None)
        if before and first_in and first_in[0] - before[-1][1] < 0.35 and not before[-1][2].endswith(SENTENCE_END):
            mid_start.append(Evidence(start=t0, end=t0 + 1, detail=f"clip {i} starts mid-sentence after "
                                                                    f"'{before[-1][2]}' -> '{first_in[2]}'"))
        inside = [w for w in words if c["src_in"] - 0.06 <= w[0] and w[1] <= c["src_out"] + 0.06]
        after = next((w for w in words if w[0] >= c["src_out"] - 0.06), None)
        if inside and after and after[0] - inside[-1][1] < 0.35 and not inside[-1][2].endswith(SENTENCE_END):
            mid_end.append(Evidence(start=t0 + dur - 1, end=t0 + dur,
                                    detail=f"clip {i} ends mid-sentence at '{inside[-1][2]}' (next '{after[2]}')"))
    out.append(_c("cut_through_word", not through, "major",
                  f"{len(through)} cut(s) through a spoken word" if through else "no cuts through words",
                  evidence=through))
    out.append(_c("dialogue_continuity", not (mid_start or mid_end), "minor",
                  f"{len(mid_start)} clip(s) start and {len(mid_end)} end mid-sentence"
                  if mid_start or mid_end else "clips start and end on sentence boundaries",
                  evidence=mid_start + mid_end))
    return out


def required_content(f: RenderFeatures, x: EvalInput) -> list[CheckResult]:
    """Spoken-phrase requirements, checked against the transcript of the OUTPUT audio."""
    said = " " + " ".join(re.sub(r"[^a-z0-9' ]+", " ", f.transcript.lower()).split()) + " "
    out = []
    for kind, items, want in (("must_include", x.must_include, True), ("must_exclude", x.must_exclude, False)):
        if not items:
            continue
        hits = {p: (" " + " ".join(re.sub(r"[^a-z0-9' ]+", " ", p.lower()).split()) + " ") in said for p in items}
        bad = [p for p, h in hits.items() if h != want]
        out.append(CheckResult(id=f"instruction.{kind}", category="instruction", kind="deterministic",
                               passed=not bad, severity="major",
                               message=("all satisfied" if not bad else
                                        f"{'missing' if want else 'present but excluded'}: {bad}"),
                               measurements={"phrases": hits},
                               explanation="Matched against a fresh transcription of the rendered audio."))
    return out
