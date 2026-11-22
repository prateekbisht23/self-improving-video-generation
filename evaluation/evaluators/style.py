"""Signal-based comparison with the reference style profile (only when a reference was given)."""

import math
import statistics

from evaluation.features import RenderFeatures
from evaluation.inputs import EvalInput
from evaluation.schemas import CheckResult
from perception.style import color_stats


def _c(id_, passed, message, **kw) -> CheckResult:
    return CheckResult(id=f"style.{id_}", category="style", kind="signal", passed=passed, severity="minor",
                       message=message, **kw)


def run(f: RenderFeatures, x: EvalInput) -> list[CheckResult]:
    ref = x.reference
    if not ref or not f.readable:
        return []
    out = []
    shots = [s.end - s.start for s in f.shots] or [f.duration]
    mine, theirs = statistics.median(shots), ref["shots"]["median"]
    sim = min(mine, theirs) / max(mine, theirs) if max(mine, theirs) > 0 else 1.0
    out.append(_c("shot_length_similarity", sim >= 0.5, f"median shot {mine:.1f}s vs reference {theirs:.1f}s",
                  score=round(sim, 3), measurements={"render_median": round(mine, 2), "reference_median": theirs}))

    c = color_stats([p for _, p in f.frames])
    rc = ref["color"]
    d = math.dist((c.brightness, c.saturation, c.warmth), (rc["brightness"], rc["saturation"], rc["warmth"]))
    score = max(0.0, 1 - d / 0.3)
    out.append(_c("color_similarity", score >= 0.5, f"colour distance {d:.3f} (brightness/saturation/warmth)",
                  score=round(score, 3), measurements={"render": c.model_dump(), "reference": rc}))

    obs = ref.get("observed") or {}
    if "captions_present" in obs:
        has = bool((x.timeline or {}).get("captions"))
        if x.captions_required is not None:
            out.append(_c("caption_match", None, "captions dictated by the instructions, not the reference"))
        else:
            out.append(_c("caption_match", has == obs["captions_present"],
                          f"render captions={has}, reference captions={obs['captions_present']}"))
    return out
