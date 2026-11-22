"""Offline evaluation of next-action predictors (PRD FR-07).

    uv run python -m agent.prediction.evaluate [--no-llm]

Data: every logged agent action (agent_actions) with the timeline state before it. Sessions created
for HOLDOUT benchmark tasks are excluded entirely. Two protocols:
  cv        5-fold GroupKFold by session over all allowed sessions (rules, markov, learned)
  val       train on non-validation sessions, test on validation-benchmark sessions (all four incl. LLM);
            these predictions are stored in action_predictions
"""

import argparse
import json
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from agent.prediction.features import ACTIONS, STAGE_OF, featurize
from agent.prediction.predictors import LearnedPredictor, LLMPredictor, MarkovPredictor, RulePredictor
from benchmarks.schemas.task import load_tasks
from config.settings import get_settings
from db.models import ActionPrediction, EditingSession
from db.session import session_scope

OUT = Path(__file__).resolve().parents[2] / "benchmarks" / "results"


def build_dataset() -> list[dict]:
    allowed = {t.id: t.split for t in load_tasks(["development", "validation"])}
    rows = []
    with session_scope() as s:
        for e in s.scalars(select(EditingSession)):
            task = (e.constraints or {}).get("benchmark_task")
            if task and task not in allowed:
                continue  # holdout (or unknown) benchmark task: never used
            versions = {v.version: v.timeline for v in e.versions}
            c = e.constraints or {}
            mem = " ".join(m.get("statement", "") for m in (e.memory_used or []))
            history: list[tuple[str, bool, str]] = []
            for a in sorted(e.actions, key=lambda a: a.step):
                if a.name in ACTIONS and a.source != "user":
                    f = featurize(versions.get(a.version_before), history, e.instructions,
                                  c.get("min_duration", 15), c.get("max_duration", 30), mem)
                    rows.append({"session": str(e.id), "step": a.step, "split": allowed.get(task, "other"),
                                 "source": a.source, "stage": STAGE_OF.get(a.name, "other"), "x": f, "y": a.name})
                history.append((a.name, a.ok, a.source))
    return rows


def score(pairs: list[tuple[list[str] | None, str, dict]]) -> dict:
    """None = the predictor errored (e.g. API quota): excluded from accuracy, reported as coverage."""
    errors = sum(p is None for p, _, _ in pairs)
    pairs = [(p, y, m) for p, y, m in pairs if p is not None]
    n = len(pairs)
    if not n:
        return {"n": 0, "errors": errors, "coverage": 0.0}
    out = {"n": n, "errors": errors, "coverage": round(n / (n + errors), 3),
           "top1": round(sum(p[:1] == [y] for p, y, _ in pairs) / n, 3),
           "top3": round(sum(y in p[:3] for p, y, _ in pairs) / n, 3),
           "valid_rate": round(sum(bool(p) and all(a in ACTIONS for a in p) for p, _, _ in pairs) / n, 3)}
    for key in ("stage", "source"):
        groups = defaultdict(list)
        for p, y, meta in pairs:
            groups[meta[key]].append(p[:1] == [y])
        out[f"top1_by_{key}"] = {k: f"{sum(v) / len(v):.2f} (n={len(v)})" for k, v in sorted(groups.items())}
    return out


def run_predictor(model, rows) -> tuple[list[tuple[list[str], str, dict]], list[float]]:
    pairs, lat = [], []
    for r in rows:
        t0 = time.perf_counter()
        try:
            pred = model.predict(r["x"])
        except Exception:
            pred = None
        lat.append((time.perf_counter() - t0) * 1000)
        pairs.append((pred, r["y"], r))
    return pairs, lat


def cross_validate(rows, k=5) -> dict:
    from sklearn.model_selection import GroupKFold

    groups = [r["session"] for r in rows]
    results = {}
    for make in (RulePredictor, MarkovPredictor, LearnedPredictor):
        pairs_all = []
        for tr, te in GroupKFold(n_splits=k).split(rows, groups=groups):
            m = make().fit([rows[i]["x"] for i in tr], [rows[i]["y"] for i in tr])
            pairs, _ = run_predictor(m, [rows[i] for i in te])
            pairs_all += pairs
        results[make().name.split("-")[0] if make is not RulePredictor else "rules-v1"] = score(pairs_all)
    return results


def validation_protocol(rows, use_llm: bool) -> dict:
    train = [r for r in rows if r["split"] != "validation"]
    test = [r for r in rows if r["split"] == "validation"]
    models = [RulePredictor(), MarkovPredictor(), LearnedPredictor()]
    if use_llm:
        models.append(LLMPredictor())
    out = {"train_examples": len(train), "test_examples": len(test),
           "train_sessions": len({r["session"] for r in train}), "test_sessions": len({r["session"] for r in test})}
    for m in models:
        m.fit([r["x"] for r in train], [r["y"] for r in train])
        pairs, lat = run_predictor(m, test)
        ok_lat = [ms for (p, _, _), ms in zip(pairs, lat, strict=True) if p is not None] or [0.0]
        out[m.name] = score(pairs) | {"latency_ms_p50": round(statistics.median(ok_lat), 2),
                                      "latency_ms_max": round(max(ok_lat), 2)}
        with session_scope() as s:  # FR-07: prediction results are stored
            for (pred, y, r), ms in zip(pairs, lat, strict=True):
                if pred is None:
                    continue
                s.add(ActionPrediction(session_id=r["session"], step=r["step"], predictor=m.name, mode="offline",
                                       predicted=pred, actual=y, stage=r["stage"], correct_top1=pred[:1] == [y],
                                       correct_top3=y in pred[:3], valid=bool(pred) and all(a in ACTIONS for a in pred),
                                       latency_ms=round(ms, 2)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    get_settings()
    rows = build_dataset()
    labels = defaultdict(int)
    for r in rows:
        labels[r["y"]] += 1
    report = {"created": datetime.now(UTC).isoformat(timespec="seconds"), "examples": len(rows),
              "sessions": len({r["session"] for r in rows}), "label_counts": dict(sorted(labels.items())),
              "majority_baseline_top1": round(max(labels.values()) / len(rows), 3),
              "cv_5fold_by_session": cross_validate(rows), "validation_split": validation_protocol(rows, not a.no_llm)}
    OUT.mkdir(exist_ok=True)
    path = OUT / f"prediction-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"report: {path}")


if __name__ == "__main__":
    main()
