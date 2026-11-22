"""Run one agent version on benchmark splits, reusing an existing comparable run when there is one.

A results file can stand in for a fresh run only if EVERYTHING that affects the outcome matches:
agent version, evaluator version, dataset version, splits, planner + judge models, and every task
finished. Otherwise the version is (re)run. Runs are resumable: the results path is fixed up front,
so a run stopped by the daily quota continues where it stopped.
"""

import json
from pathlib import Path

from benchmarks.runner import RESULTS, run_benchmark
from benchmarks.schemas.task import BenchmarkTask, dataset_version
from config.models import model_id
from evaluation.schemas import EVALUATOR_VERSION

EXPERIMENTS = RESULTS / "experiments"


def comparable(run: dict, version: str, splits: list[str], n_tasks: int) -> bool:
    return (run.get("agent_version") == version and run.get("evaluator_version") == EVALUATOR_VERSION
            and run.get("dataset_version") == dataset_version() and sorted(run.get("splits", [])) == sorted(splits)
            and run.get("models", {}).get("planner") == model_id("planner")
            and run.get("models", {}).get("judge") == model_id("judge")
            and len(run.get("results", [])) == n_tasks
            and all(r.get("status") != "error" and not r.get("judge_errors") for r in run["results"]))


def find_run(version: str, splits: list[str], n_tasks: int) -> Path | None:
    files = [p for d in (RESULTS, EXPERIMENTS) if d.exists() for p in d.glob("*.json")
             if not p.name.startswith("prediction-") and not p.name.endswith(".stability.json")]
    for p in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            run = json.loads(p.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(run, dict) and comparable(run, version, splits, n_tasks):
            return p
    return None


def run_version(version: str, tasks: list[BenchmarkTask], splits: list[str], path: Path) -> tuple[dict, Path]:
    """Reuse a comparable run, else run (or resume) into `path`."""
    found = find_run(version, splits, len(tasks))
    if found:
        return json.loads(found.read_text()), found
    EXPERIMENTS.mkdir(parents=True, exist_ok=True)
    return run_benchmark(tasks, splits=splits, agent_version=version, path=path)
