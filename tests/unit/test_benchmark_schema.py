from pathlib import Path

from benchmarks.schemas.task import BenchmarkTask

ROOT = Path(__file__).resolve().parents[2]


def test_example_tasks_load():
    tasks = [BenchmarkTask.load(p) for p in (ROOT / "benchmarks").rglob("*.yaml")]
    assert tasks and all(t.split in ("development", "validation", "holdout") for t in tasks)
