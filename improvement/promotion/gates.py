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

Scoped candidates (AgentConfig.scope): the gates judge the IN-SCOPE comparison only, and every check
change must also beat that check's own A/A noise, measured on the out-of-scope tasks of the same
experiment (they ran the baseline's code): a one-sided binomial test, P(>= k of n tasks moving the same
way by noise alone) < ALPHA, where each task moves that way with probability (control flip rate)/2.
A check without control data gets the noisiest control rate (conservative). With a handful of
in-scope tasks the paired mean only gates if its whole 95% CI is below zero, and the validation-split
rule needs >= MIN_SPLIT tasks; anything else would be a coin flip.

The critical rates use `after_rerun`: a task that failed once and passed its confirmation re-run
(render or technical gate) is flaky, not a regression.
"""

import json
import math
from pathlib import Path

REGRESSION_DROP = 0.10
MIN_TARGET_GAIN = 0.10
VAL_TOLERANCE = 0.02
MIN_FLIPS = 2
ALPHA = 0.05
NOISE_FLOOR = 0.02   # never assume a check is noiseless
MIN_SPLIT = 3
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


def binom_tail(k: int, n: int, q: float) -> float:
    """P(X >= k) for X ~ Binomial(n, q)."""
    return sum(math.comb(n, i) * q ** i * (1 - q) ** (n - i) for i in range(k, n + 1))


def noise_rates(control: dict[str, dict]) -> tuple[dict[str, float], float]:
    rates = {k: max(v["flips"] / v["n"], NOISE_FLOOR) for k, v in control.items() if v["n"] >= 5}
    return rates, max(rates.values(), default=0.5)


def evaluate_gates(cmp: dict, targets: list[str], advisory: dict[str, str] | None = None) -> dict:
    advisory = advisory or {}
    scoped = "scope" in cmp
    view = cmp["scope"] if scoped else cmp
    rates, worst = noise_rates(cmp["control"]["checks"]) if scoped else ({}, 0.5)
    critical, regressions, improvements, notes = [], [], [], []

    def beyond_noise(cid: str, flips: int, n: int) -> tuple[bool, str]:
        if not scoped:
            return True, ""
        q = rates.get(cid, worst) / 2
        p = binom_tail(flips, n, q)
        return p < ALPHA, f"p={p:.3f} vs A/A flip rate {2 * q:.0%}"

    m = view.get("after_rerun") or view["metrics"]
    for k in ("completion_rate", "technical_valid_rate"):
        d = m[k]["delta"]
        if d is not None and d < 0:
            critical.append(f"{k} dropped {m[k]['baseline']} -> {m[k]['candidate']}")
    failed = view.get("confirmed_failed", view["newly_failed"])
    if failed:
        how = "confirmed by a re-run" if cmp.get("rerun") else "not re-run"
        critical.append(f"tasks no longer render ({how}): {failed}")
    if view.get("gate_confirmed_failed"):
        how = "confirmed by a re-run" if cmp.get("rerun") else "not re-run"
        notes.append(f"technical gate newly failed ({how}): {view['gate_confirmed_failed']}")
    for key, what in (("flaky", "failed once, rendered on the re-run"),
                      ("gate_flaky", "failed the technical gate once, passed on the re-run")):
        if view.get(key):
            notes.append(f"{what} (flaky, not gating): {view[key]}")
    if cmp.get("excluded_infra_errors"):
        notes.append(f"excluded (infrastructure errors, not agent behaviour): {cmp['excluded_infra_errors']}")
    if scoped:
        moved = {k: f"{v['flips']}/{v['n']}" for k, v in cmp["control"]["checks"].items() if v["flips"]}
        notes.append(f"scope '{view['name']}': gates use the {view['tasks']} in-scope tasks; the "
                     f"{len(cmp['control']['task_ids'])} others ran the baseline's code (A/A control). "
                     f"Control flips: {moved or 'none'}")
        if cmp["newly_failed"] != view["newly_failed"] or cmp.get("gate_failed") != view.get("gate_failed"):
            notes.append(f"out-of-scope (noise by construction): render failures {cmp['newly_failed']}, "
                         f"technical gate {cmp.get('gate_failed')}")
    for cid, v in view["checks"].items():
        if v["delta"] is None:
            continue
        flips = round(abs(v["delta"]) * v["n"])
        line = f"{cid}: {v['baseline']:.0%} -> {v['candidate']:.0%} (n={v['n']})"
        sig, why = beyond_noise(cid, flips, v["n"])
        if cid in targets:
            ok = v["delta"] >= MIN_TARGET_GAIN and flips >= MIN_FLIPS and sig
            (improvements if ok else notes).append(f"target {line}" + (f", {why}" if why else ""))
        elif v["delta"] < -REGRESSION_DROP and flips < MIN_FLIPS:
            notes.append(f"{line}: {flips} task flipped, below {MIN_FLIPS}; not gating")
        elif v["delta"] < -REGRESSION_DROP and not sig:
            notes.append(f"{line}: within A/A noise ({why}); not gating")
        elif v["delta"] < -REGRESSION_DROP:
            if cid in advisory:
                notes.append(f"advisory (not gating) {line}: {advisory[cid]}")
            else:
                regressions.append(line + (f", {why}" if why else ""))
    val = view["by_split"].get("validation")
    if val and val["delta"] < -VAL_TOLERANCE:
        if scoped and val["n"] < MIN_SPLIT:
            notes.append(f"validation mean {val['baseline']} -> {val['candidate']} on {val['n']} in-scope "
                         f"task(s), below {MIN_SPLIT}; not gating")
        else:
            regressions.append(f"validation mean pass rate {val['baseline']} -> {val['candidate']}")
    pr = view["paired"]
    if pr["mean_diff"] < 0:
        line = f"paired mean pass-rate difference {pr['mean_diff']:+.3f} (95% CI {pr['ci95']})"
        if scoped and pr["ci95"][1] >= 0:
            notes.append(f"{line}: CI includes 0 on {view['tasks']} in-scope tasks; not gating")
        else:
            regressions.append(line)
    if not improvements:
        notes.append(f"no targeted check improved by >= {MIN_TARGET_GAIN:.0%}"
                     + (" beyond A/A noise" if scoped else ""))
    eligible = not critical and not regressions and bool(improvements)
    return {"eligible": eligible, "critical": critical, "regressions": regressions, "improvements": improvements,
            "notes": notes, "advisory_checks": sorted(advisory), "scope": view.get("name") if scoped else None,
            "thresholds": {"regression_drop": REGRESSION_DROP, "min_target_gain": MIN_TARGET_GAIN,
                           "validation_tolerance": VAL_TOLERANCE, "min_flips": MIN_FLIPS,
                           **({"alpha": ALPHA, "noise_floor": NOISE_FLOOR} if scoped else {})}}
