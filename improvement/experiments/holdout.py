"""Final holdout assessment of a candidate that already passed the regression gates.

This is the ONLY module under improvement/ allowed to load holdout tasks (enforced by a test).
It runs after candidate selection, and its numbers go to the experiment record and the human
approval report only: no diagnosis or candidate-generation step ever reads them, so the holdout
stays an independent estimate.
"""

import json

from benchmarks.schemas.task import in_scope, load_tasks
from db.session import session_scope
from improvement import registry
from improvement.experiments.compare import compare
from improvement.experiments.run import EXPERIMENTS, run_pair

SPLITS = ["holdout"]


def assess(experiment_id: str, baseline_version: str, candidate_version: str) -> dict:
    tasks = load_tasks(SPLITS, allow_holdout=True)
    tag = experiment_id[:8]
    base_path, cand_path = run_pair(baseline_version, candidate_version, tasks, SPLITS,
                                    EXPERIMENTS / f"{tag}-baseline-hol.json", EXPERIMENTS / f"{tag}-candidate-hol.json")
    base, cand = json.loads(base_path.read_text()), json.loads(cand_path.read_text())
    with session_scope() as s:
        name = registry.get(s, candidate_version).scope()
    scope = {"name": name, "tasks": [t.id for t in tasks if in_scope(t, name)]} if name else None
    cmp = compare(base, cand, scope=scope)
    out = {"baseline_run": str(base_path), "candidate_run": str(cand_path), "metrics": cmp["metrics"],
           "paired": cmp["paired"], "checks": cmp["checks"], "newly_failed": cmp["newly_failed"],
           "newly_rendered": cmp["newly_rendered"]}
    if scope:  # the in-scope tasks are the evidence; the rest ran the baseline's code
        out["scope"] = {k: cmp["scope"][k] for k in ("name", "task_ids", "metrics", "paired", "checks")}
        out["control"] = cmp["control"]
    return out
