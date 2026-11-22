from collections import Counter

import pytest

from benchmarks.runner import summarize
from benchmarks.schemas.task import HoldoutAccessError, dataset_version, load_tasks


def test_benchmark_has_30_tasks_with_prd_splits_and_categories():
    tasks = load_tasks(["development", "validation", "holdout"], allow_holdout=True)
    assert Counter(t.split for t in tasks) == {"development": 18, "validation": 6, "holdout": 6}
    assert Counter(t.category for t in tasks) == {"instruction_following": 8, "pacing_scene_selection": 7,
                                                  "reference_style": 5, "audio_captions": 5, "personalization": 5}
    assert all(t.constraints.min_duration <= t.constraints.max_duration for t in tasks)


def test_holdout_requires_explicit_opt_in():
    with pytest.raises(HoldoutAccessError):
        load_tasks(["development", "holdout"])
    assert all(t.split != "holdout" for t in load_tasks(["development", "validation"]))


def test_dataset_version_is_stable_content_hash():
    assert dataset_version() == dataset_version() and dataset_version().startswith("bench-v1-")


def test_summary_counts_failures_against_completion():
    r = [{"task": "a", "category": "x", "evaluation_id": "1", "gate": True, "pass_rate": 0.8, "steps": 6,
          "repairs": 1, "checks": {"c1": True, "c2": False}},
         {"task": "b", "category": "x", "status": "error"}]
    s = summarize(r)
    assert s["completion_rate"] == 0.5 and s["technical_valid_rate"] == 0.5
    assert s["check_pass_rates"] == {"c1": 1.0, "c2": 0.0}
