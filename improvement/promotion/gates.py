"""Regression gates (PRD Phase 5 §6): may this candidate even be put in front of a human?

A candidate is ELIGIBLE only if all of these hold (dev + validation comparison):
  critical  - completion rate does not drop
            - technical-gate pass rate does not drop (candidates cannot bypass technical quality)
            - no task that rendered under the baseline fails to render under the candidate
  regression- no non-targeted, non-advisory check drops by more than REGRESSION_DROP
  improvement - at least one targeted check improves by >= MIN_TARGET_GAIN
            - the validation split's mean pass rate does not drop by more than VAL_TOLERANCE
            - the paired mean pass-rate difference is not negative

Advisory checks (too noisy to gate on) are reported but never block. They come from the
evaluator-stability measurement: model checks whose verdicts flip on re-evaluation of the SAME render.
Thresholds are deliberately coarse: with 24 tasks, one task flipping a check moves it ~4-6 points.
"""

import json
from pathlib import Path

REGRESSION_DROP = 0.10
MIN_TARGET_GAIN = 0.10
VAL_TOLERANCE = 0.02
STABILITY_MIN_AGREEMENT = 0.85
RESULTS = Path(__file__).resolve().parents[2] / "benchmarks" / "results"


def advisory_checks(results_dir: Path = RESULTS) -> dict[str, str]:
    """Checks whose own re-evaluation agreement is below STABILITY_MIN_AGREEMENT (latest stability run)."""
    files = sorted(results_dir.glob("*.stability.json"))
    if not files:
        return {}
    st = json.loads(files[-1].read_text())
    flips: dict[str, int] = {}
    for f in st.get("flips", []):  # "task check.id: before -> after"
        cid = f.split(" ")[1].rstrip(":")
        flips[cid] = flips.get(cid, 0) + 1
    src = results_dir / f"{st['source_run']}.json"
    n = sum(1 for r in json.loads(src.read_text())["results"] if r.get("render_id")) if src.exists() else 0
    out = {}
    for cid, k in flips.items():
        if n and 1 - k / n < STABILITY_MIN_AGREEMENT:
            out[cid] = f"verdict flipped on {k}/{n} re-evaluations of identical renders ({st['source_run']})"
    return out


def evaluate_gates(cmp: dict, targets: list[str], advisory: dict[str, str] | None = None) -> dict:
    advisory = advisory or {}
    m = cmp["metrics"]
    critical, regressions, improvements, notes = [], [], [], []
    for k in ("completion_rate", "technical_valid_rate"):
        d = m[k]["delta"]
        if d is not None and d < 0:
            critical.append(f"{k} dropped {m[k]['baseline']} -> {m[k]['candidate']}")
    if cmp["newly_failed"]:
        critical.append(f"tasks no longer render: {cmp['newly_failed']}")
    for cid, v in cmp["checks"].items():
        if v["delta"] is None:
            continue
        if cid in targets:
            (improvements if v["delta"] >= MIN_TARGET_GAIN else notes).append(
                f"target {cid}: {v['baseline']:.0%} -> {v['candidate']:.0%} (n={v['n']})")
        elif v["delta"] < -REGRESSION_DROP:
            line = f"{cid}: {v['baseline']:.0%} -> {v['candidate']:.0%} (n={v['n']})"
            if cid in advisory:
                notes.append(f"advisory (not gating) {line}: {advisory[cid]}")
            else:
                regressions.append(line)
    val = cmp["by_split"].get("validation")
    if val and val["delta"] < -VAL_TOLERANCE:
        regressions.append(f"validation mean pass rate {val['baseline']} -> {val['candidate']}")
    if cmp["paired"]["mean_diff"] < 0:
        regressions.append(f"paired mean pass-rate difference {cmp['paired']['mean_diff']:+.3f} "
                           f"(95% CI {cmp['paired']['ci95']})")
    if not improvements:
        notes.append(f"no targeted check improved by >= {MIN_TARGET_GAIN:.0%}")
    eligible = not critical and not regressions and bool(improvements)
    return {"eligible": eligible, "critical": critical, "regressions": regressions, "improvements": improvements,
            "notes": notes, "advisory_checks": sorted(advisory),
            "thresholds": {"regression_drop": REGRESSION_DROP, "min_target_gain": MIN_TARGET_GAIN,
                           "validation_tolerance": VAL_TOLERANCE}}
