"""Caption checks against an independent transcription of the rendered audio.

Caveat (documented in the report): both captions and the reference transcript come from
Whisper (source vs output audio). WER here measures *consistency*, not ground-truth accuracy.
"""

import re

import jiwer

from evaluation.features import RenderFeatures
from evaluation.inputs import EvalInput
from evaluation.schemas import CheckResult, Evidence


def _norm(s: str) -> list[str]:
    s = s.lower().replace("-", " ")
    return re.sub(r"[^a-z0-9' ]+", " ", s).split()


def _c(id_, passed, severity, message, kind="signal", **kw) -> CheckResult:
    return CheckResult(id=f"captions.{id_}", category="captions", kind=kind, passed=passed, severity=severity,
                       message=message, **kw)


def _speech_spans(words, gap=0.3):
    spans = []
    for w in words:
        if spans and w.start - spans[-1][1] <= gap:
            spans[-1][1] = max(spans[-1][1], w.end)
        else:
            spans.append([w.start, w.end])
    return spans


def run(f: RenderFeatures, x: EvalInput) -> list[CheckResult]:
    caps = (x.timeline or {}).get("captions", [])
    out = []
    if x.captions_required is not None or caps:
        present = bool(caps)
        out.append(_c("present", present if x.captions_required else None, "major",
                      f"{len(caps)} caption cards", kind="deterministic"))
    if not caps or not f.words:
        return out

    ref, hyp = _norm(f.transcript), _norm(" ".join(c["text"] for c in caps))
    o = jiwer.process_words(" ".join(ref), " ".join(hyp))
    examples = []
    for chunk in o.alignments[0]:
        if chunk.type == "substitute" and len(examples) < 5:
            examples.append(f"heard '{' '.join(ref[chunk.ref_start_idx:chunk.ref_end_idx])}' vs caption "
                            f"'{' '.join(hyp[chunk.hyp_start_idx:chunk.hyp_end_idx])}'")
    out.append(_c("accuracy", o.wer <= 0.15, "minor", f"caption WER {o.wer:.1%} vs transcription of output audio",
                  score=round(max(0.0, 1 - o.wer), 3),
                  measurements={"wer": round(o.wer, 4), "substitutions": o.substitutions,
                                "deletions": o.deletions, "insertions": o.insertions, "examples": examples},
                  explanation="Both sides are ASR (source vs output audio): measures consistency, not truth."))

    # sync: caption start vs the matching spoken word in the output audio
    offsets = []
    for c in caps:
        first = (_norm(c["text"]) or [""])[0]
        cands = [w for w in f.words if _norm(w.text)[:1] == [first] and abs(w.start - c["start"]) <= 1.5]
        if cands:
            w = min(cands, key=lambda w: abs(w.start - c["start"]))
            offsets.append((c["start"] - w.start, c))
    if offsets:
        mean_abs = sum(abs(o) for o, _ in offsets) / len(offsets)
        worst = sorted(offsets, key=lambda t: -abs(t[0]))[:3]
        out.append(_c("sync", mean_abs <= 0.25, "major", f"mean |offset| {mean_abs * 1000:.0f} ms over "
                      f"{len(offsets)}/{len(caps)} matched cards",
                      measurements={"mean_abs_offset_s": round(mean_abs, 3), "matched": len(offsets)},
                      evidence=[Evidence(start=c["start"], end=c["end"], detail=f"'{c['text']}' off by {o:+.2f}s")
                                for o, c in worst if abs(o) > 0.25]))

    spans = _speech_spans(f.words)
    total = sum(e - s for s, e in spans)
    covered = sum(max(0.0, min(e, c["end"]) - max(s, c["start"])) for s, e in spans for c in caps)
    cov = covered / total if total else 1.0
    out.append(_c("speech_coverage", cov >= 0.8, "minor", f"captions cover {cov:.0%} of speech",
                  score=round(min(cov, 1.0), 3), measurements={"coverage": round(cov, 3)}))
    return out
