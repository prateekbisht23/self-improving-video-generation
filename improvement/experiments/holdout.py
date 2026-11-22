"""Final holdout assessment of a candidate that already passed the regression gates.

This is the ONLY module under improvement/ allowed to load holdout tasks (enforced by a test).
It runs after candidate selection, and its numbers go to the experiment record and the human
approval report only: no diagnosis or candidate-generation step ever reads them, so the holdout
stays an independent estimate.
"""

from benchmarks.schemas.task import load_tasks
from improvement.experiments.compare import compare
from improvement.experiments.run import EXPERIMENTS, run_version

SPLITS = ["holdout"]


def assess(experiment_id: str, baseline_version: str, candidate_version: str) -> dict:
    tasks = load_tasks(SPLITS, allow_holdout=True)
    tag = experiment_id[:8]
    base, base_path = run_version(baseline_version, tasks, SPLITS, EXPERIMENTS / f"{tag}-baseline-hol.json")
    cand, cand_path = run_version(candidate_version, tasks, SPLITS, EXPERIMENTS / f"{tag}-candidate-hol.json")
    cmp = compare(base, cand)
    return {"baseline_run": str(base_path), "candidate_run": str(cand_path), "metrics": cmp["metrics"],
            "paired": cmp["paired"], "checks": cmp["checks"], "newly_failed": cmp["newly_failed"],
            "newly_rendered": cmp["newly_rendered"]}
