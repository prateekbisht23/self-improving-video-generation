"""Baseline vs candidate comparison on the same tasks (pure functions over two results files).

- Per-check pass rates (+ delta) over tasks both runs finished: the fair comparison.
- Run-level metrics (completion, technical validity) over ALL tasks: a candidate that stops
  rendering some tasks must not look better because those tasks drop out of the averages.
- Paired task-level differences of pass rate (an unrendered task counts as 0), with a bootstrap
  confidence interval for the mean difference. Paired because tasks differ far more from each other
  than versions do; comparing each task with itself removes that variance.
- Infrastructure errors (status "error": network down, provider exception) are not agent behaviour:
  such a task is excluded on BOTH sides and listed. Round 3 lost a baseline task to a DNS outage.
- A task that newly fails under the candidate is "confirmed" only if a re-run of the candidate fails
  again (`confirm` run); otherwise it is reported as flaky. One run per version cannot tell one bad
  draw from a regression (the unchanged baseline itself failed if-02 on one of three runs). The same
  holds for a task that newly fails the TECHNICAL GATE. `after_rerun` recomputes completion and
  technical validity with flaky tasks taking their re-run result; the critical gates use it.
- Scope: when the candidate's changes can only act on some tasks (AgentConfig.scope), tasks outside
  it run the baseline's code. Their differences are noise by construction, so `scope` holds the
  comparison over in-scope tasks only, and `control` the per-check flip counts outside it: an A/A
  noise measurement taken in the same experiment, under the same provider conditions.
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


def _rates(rows: list[dict]) -> dict:
    n = len(rows) or 1
    return {"completion_rate": round(sum(bool(r.get("evaluation_id")) for r in rows) / n, 3),
            "technical_valid_rate": round(sum(bool(r.get("gate")) for r in rows) / n, 3)}


def _flips(b: dict, c: dict, tasks: list[str]) -> dict[str, dict]:
    """Per check: on how many tasks (both rendered) did the verdict change?"""
    out: dict[str, dict] = {}
    for t in tasks:
        if not (b[t].get("evaluation_id") and c[t].get("evaluation_id")):
            continue
        for k, v in b[t]["checks"].items():
            w = c[t]["checks"].get(k)
            if v is not None and w is not None:
                f = out.setdefault(k, {"n": 0, "flips": 0})
                f["n"] += 1
                f["flips"] += int(v != w)
    return out


def _core(b: dict, c: dict, tasks: list[str], bs: dict, cs: dict, rerun: dict) -> dict:
    both_done = {t for t in tasks if b[t].get("evaluation_id") and c[t].get("evaluation_id")}
    bs = bs | _rates([b[t] for t in tasks])  # over comparable tasks only (infrastructure errors excluded)
    cs = cs | _rates([c[t] for t in tasks])
    metrics = {k: {"baseline": bs.get(k), "candidate": cs.get(k),
                   "delta": round(cs[k] - bs[k], 3) if bs.get(k) is not None and cs.get(k) is not None else None}
               for k in RUN_METRICS}
    br = check_rates([b[t] for t in tasks], both_done)
    cr = check_rates([c[t] for t in tasks], both_done)
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
    newly_failed = sorted(t for t in tasks if b[t].get("evaluation_id") and not c[t].get("evaluation_id"))
    flaky = [t for t in newly_failed if (rerun.get(t) or {}).get("evaluation_id")]
    gate_failed = sorted(t for t in both_done if b[t].get("gate") and not c[t].get("gate"))
    gate_flaky = [t for t in gate_failed if (rerun.get(t) or {}).get("gate")]
    redo = set(flaky) | set(gate_flaky)
    after = _rates([rerun[t] if t in redo else c[t] for t in tasks])
    after_rerun = {k: {"baseline": bs[k], "candidate": after[k], "delta": round(after[k] - bs[k], 3)}
                   for k in after}
    return {"tasks": len(tasks), "both_rendered": len(both_done), "metrics": metrics, "checks": checks,
            "by_split": by_split, "after_rerun": after_rerun,
            "paired": {"mean_diff": round(statistics.fmean(d), 4) if d else 0.0, "ci95": bootstrap_ci(d),
                       "wins": sum(x > 0.001 for x in d), "ties": sum(abs(x) <= 0.001 for x in d),
                       "losses": sum(x < -0.001 for x in d), "per_task": diffs},
            "newly_failed": newly_failed, "flaky": flaky,
            "confirmed_failed": [t for t in newly_failed if t not in flaky],
            "gate_failed": gate_failed, "gate_flaky": gate_flaky,
            "gate_confirmed_failed": [t for t in gate_failed if t not in gate_flaky],
            "newly_rendered": sorted(t for t in tasks if c[t].get("evaluation_id") and not b[t].get("evaluation_id"))}


def compare(base: dict, cand: dict, confirm: dict | None = None, scope: dict | None = None) -> dict:
    """`scope`: {"name": ..., "tasks": [in-scope task ids]} when the candidate is scoped (else None)."""
    if base["dataset_version"] != cand["dataset_version"] or base["evaluator_version"] != cand["evaluator_version"]:
        raise ValueError("runs used different dataset or evaluator versions; they are not comparable")
    b, c = _by_task(base), _by_task(cand)
    common = sorted(set(b) & set(c))
    infra = sorted(t for t in common if b[t].get("status") == "error" or c[t].get("status") == "error")
    tasks = [t for t in common if t not in infra]
    bs = {k: v for k, v in (base.get("summary") or {}).items() if k in RUN_METRICS}
    cs = {k: v for k, v in (cand.get("summary") or {}).items() if k in RUN_METRICS}
    rerun = _by_task(confirm) if confirm else {}
    out = {"baseline_version": base["agent_version"], "candidate_version": cand["agent_version"],
           **_core(b, c, tasks, bs, cs, rerun), "rerun": confirm is not None, "excluded_infra_errors": infra}
    if scope:
        inside = [t for t in tasks if t in set(scope["tasks"])]
        outside = [t for t in tasks if t not in set(scope["tasks"])]
        # run-level summaries are over all tasks: recompute them over the scope only
        keep = {"completion_rate", "technical_valid_rate"}
        out["scope"] = {"name": scope["name"], "task_ids": inside,
                        **_core(b, c, inside, {k: v for k, v in bs.items() if k in keep},
                                {k: v for k, v in cs.items() if k in keep}, rerun)}
        out["control"] = {"task_ids": outside, "checks": _flips(b, c, outside)}
    return out
