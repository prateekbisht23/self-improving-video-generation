"""Baseline vs candidate comparison on the same tasks (pure functions over two results files).

- Per-check pass rates (+ delta) over tasks both runs finished: the fair comparison.
- Run-level metrics (completion, technical validity) over ALL tasks: a candidate that stops
  rendering some tasks must not look better because those tasks drop out of the averages.
- Paired task-level differences of pass rate (an unrendered task counts as 0), with a bootstrap
  confidence interval for the mean difference. Paired because tasks differ far more from each other
  than versions do; comparing each task with itself removes that variance.
"""

import random
import statistics

RUN_METRICS = ("completion_rate", "technical_valid_rate", "mean_pass_rate", "mean_actions", "repairs_per_task")


def _by_task(run: dict) -> dict[str, dict]:
    return {r["task"]: r for r in run["results"]}


def _score(r: dict | None) -> float:
    return float(r["pass_rate"]) if r and r.get("evaluation_id") and r.get("pass_rate") is not None else 0.0


def bootstrap_ci(diffs: list[float], n: int = 4000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float]:
    if not diffs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return (round(means[int(alpha / 2 * n)], 4), round(means[int((1 - alpha / 2) * n) - 1], 4))


def check_rates(results: list[dict], tasks: set[str]) -> dict[str, tuple[int, int]]:
    out: dict[str, list[int]] = {}
    for r in results:
        if r["task"] not in tasks or not r.get("evaluation_id"):
            continue
        for k, v in r["checks"].items():
            if v is not None:
                out.setdefault(k, [0, 0])
                out[k][0] += bool(v)
                out[k][1] += 1
    return {k: (a, b) for k, (a, b) in out.items()}


def compare(base: dict, cand: dict) -> dict:
    if base["dataset_version"] != cand["dataset_version"] or base["evaluator_version"] != cand["evaluator_version"]:
        raise ValueError("runs used different dataset or evaluator versions; they are not comparable")
    b, c = _by_task(base), _by_task(cand)
    tasks = sorted(set(b) & set(c))
    both_done = {t for t in tasks if b[t].get("evaluation_id") and c[t].get("evaluation_id")}
    bs = {k: v for k, v in (base.get("summary") or {}).items() if k in RUN_METRICS}
    cs = {k: v for k, v in (cand.get("summary") or {}).items() if k in RUN_METRICS}
    metrics = {k: {"baseline": bs.get(k), "candidate": cs.get(k),
                   "delta": round(cs[k] - bs[k], 3) if bs.get(k) is not None and cs.get(k) is not None else None}
               for k in RUN_METRICS}
    br, cr = check_rates(base["results"], both_done), check_rates(cand["results"], both_done)
    checks = {}
    for k in sorted(set(br) | set(cr)):
        bp = br[k][0] / br[k][1] if k in br else None
        cp = cr[k][0] / cr[k][1] if k in cr else None
        checks[k] = {"baseline": None if bp is None else round(bp, 3),
                     "candidate": None if cp is None else round(cp, 3),
                     "n": min(br.get(k, (0, 0))[1], cr.get(k, (0, 0))[1]),
                     "delta": None if bp is None or cp is None else round(cp - bp, 3)}
    diffs = {t: round(_score(c[t]) - _score(b[t]), 4) for t in tasks}
    splits: dict[str, dict] = {}
    for t in tasks:
        sp = c[t].get("split") or b[t].get("split") or "?"
        splits.setdefault(sp, {"baseline": [], "candidate": []})
        splits[sp]["baseline"].append(_score(b[t]))
        splits[sp]["candidate"].append(_score(c[t]))
    by_split = {sp: {"n": len(v["baseline"]), "baseline": round(statistics.fmean(v["baseline"]), 3),
                     "candidate": round(statistics.fmean(v["candidate"]), 3),
                     "delta": round(statistics.fmean(v["candidate"]) - statistics.fmean(v["baseline"]), 3)}
                for sp, v in sorted(splits.items())}
    d = list(diffs.values())
    return {"baseline_version": base["agent_version"], "candidate_version": cand["agent_version"],
            "tasks": len(tasks), "both_rendered": len(both_done), "metrics": metrics, "checks": checks,
            "by_split": by_split,
            "paired": {"mean_diff": round(statistics.fmean(d), 4) if d else 0.0, "ci95": bootstrap_ci(d),
                       "wins": sum(x > 0.001 for x in d), "ties": sum(abs(x) <= 0.001 for x in d),
                       "losses": sum(x < -0.001 for x in d), "per_task": diffs},
            "newly_failed": sorted(t for t in tasks if b[t].get("evaluation_id") and not c[t].get("evaluation_id")),
            "newly_rendered": sorted(t for t in tasks if c[t].get("evaluation_id") and not b[t].get("evaluation_id"))}
