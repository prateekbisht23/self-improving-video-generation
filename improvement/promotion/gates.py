"""Regression gates (PRD Phase 5 §6): may this candidate even be put in front of a human?

A candidate is ELIGIBLE only if all of these hold (dev + validation comparison):
  critical  - completion rate does not drop
            - technical-gate pass rate does not drop (candidates cannot bypass technical quality)
            - no task that rendered under the baseline fails to render under the candidate, CONFIRMED by
              a re-run (a task that renders on the re-run is reported as flaky, not critical)
  regression- no non-targeted, non-advisory check drops by more than REGRESSION_DROP and >= MIN_FLIPS tasks
  improvement - at least one targeted check improves by >= MIN_TARGET_GAIN and >= MIN_FLIPS tasks
            - the validation split's mean pass rate does not drop by more than VAL_TOLERANCE
            - the paired mean pass-rate difference is not negative

Advisory checks (too noisy to gate on) are reported but never block. They come from the
evaluator-stability measurement: model checks whose verdicts flip on re-evaluation of the SAME render.
Thresholds are deliberately coarse: with 24 tasks, one task flipping a check moves it ~4-6 points,
and on a check that applies to 3 tasks one flip is 33 points. Hence MIN_FLIPS: a single task changing
its verdict is indistinguishable from run-to-run noise (round 2's accidental A/A test).
"""

import json
from pathlib import Path

REGRESSION_DROP = 0.10
MIN_TARGET_GAIN = 0.10
VAL_TOLERANCE = 0.02
MIN_FLIPS = 2
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
    failed = cmp.get("confirmed_failed", cmp["newly_failed"])
    if failed:
        how = "confirmed by a re-run" if cmp.get("rerun") else "not re-run"
        critical.append(f"tasks no longer render ({how}): {failed}")
    if cmp.get("flaky"):
        notes.append(f"failed once, rendered on the re-run (flaky, not gating): {cmp['flaky']}")
    if cmp.get("excluded_infra_errors"):
        notes.append(f"excluded (infrastructure errors, not agent behaviour): {cmp['excluded_infra_errors']}")
    for cid, v in cmp["checks"].items():
        if v["delta"] is None:
            continue
        flips = round(abs(v["delta"]) * v["n"])
        if cid in targets:
            ok = v["delta"] >= MIN_TARGET_GAIN and flips >= MIN_FLIPS
            (improvements if ok else notes).append(
                f"target {cid}: {v['baseline']:.0%} -> {v['candidate']:.0%} (n={v['n']})")
        elif v["delta"] < -REGRESSION_DROP and flips < MIN_FLIPS:
            notes.append(f"{cid}: {v['baseline']:.0%} -> {v['candidate']:.0%} (n={v['n']}): "
                         f"{flips} task flipped, below {MIN_FLIPS}; not gating")
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
                           "validation_tolerance": VAL_TOLERANCE, "min_flips": MIN_FLIPS}}
