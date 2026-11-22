"""Failure clustering (FR-11): rule-based first, semantic where it helps.

1. Rule clusters: one per failed check id (plus normalised agent errors for edits that never
   rendered). The check id already IS a category the evaluator defined, so this is cheap and exact.
2. Semantic sub-clusters: model-judge failures share a check id but fail for different reasons
   ("weak hook" vs "abrupt ending" for narrative.structure). Their free-text explanations are
   embedded and grouped by agglomerative clustering on cosine distance. Template messages from
   deterministic checks ("2 clip(s) start mid-sentence") gain nothing from embeddings, so they are
   left as rule clusters.

Clusters are ranked by impact = severity weight x share of renders affected.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from improvement.collection import FailureRecord, FailureSet

SEVERITY_WEIGHT = {"critical": 4.0, "major": 2.0, "minor": 1.0, "info": 0.5}
SEMANTIC_MIN = 4             # only split clusters with at least this many records
SEMANTIC_THRESHOLD = 0.35    # cosine distance for merging (average linkage)


@dataclass
class Cluster:
    key: str
    method: str
    check_id: str
    category: str
    severity: str
    label: str
    records: list[FailureRecord] = field(default_factory=list)
    rate: float = 0.0

    @property
    def tasks(self) -> list[str]:
        return sorted({r.task for r in self.records})

    @property
    def n_sessions(self) -> int:
        return len({r.session_id for r in self.records})

    @property
    def impact(self) -> float:
        return round(SEVERITY_WEIGHT.get(self.severity, 1.0) * self.rate, 3)

    def examples(self, k: int = 5) -> list[dict]:
        seen, out = set(), []
        for r in self.records:
            if r.task in seen:
                continue
            seen.add(r.task)
            out.append({"issue_id": r.issue_id, "task": r.task, "session_id": r.session_id,
                        "message": r.message, "explanation": r.explanation[:400],
                        "evidence": [e.get("detail") for e in r.evidence][:4], "trace_id": r.trace_id})
            if len(out) == k:
                break
        return out


def _worst(records: list[FailureRecord]) -> str:
    return max((r.severity for r in records), key=lambda x: SEVERITY_WEIGHT.get(x, 0))


def rule_clusters(fs: FailureSet) -> list[Cluster]:
    groups: dict[str, list[FailureRecord]] = defaultdict(list)
    for r in fs.records:
        key = r.check_id if r.check_id != "agent.no_render" else f"agent.no_render:{r.message}"
        groups[key].append(r)
    out = []
    for key, recs in groups.items():
        r0 = recs[0]
        label = (f"edit not rendered: {r0.message}" if r0.check_id == "agent.no_render"
                 else f"{r0.check_id} fails")
        denom = fs.sessions if r0.check_id == "agent.no_render" else max(fs.evaluated_checks.get(r0.check_id, 0), 1)
        c = Cluster(key, "rule", r0.check_id, r0.category, _worst(recs), label, recs)
        c.rate = round(len({x.session_id for x in recs}) / max(denom, 1), 3)
        out.append(c)
    return sorted(out, key=lambda c: -c.impact)


def semantic_split(c: Cluster, embed: Callable[[list[str]], list[list[float]]],
                   threshold: float = SEMANTIC_THRESHOLD) -> list[Cluster]:
    """Split one rule cluster of model-judge failures by meaning. Returns [c] when nothing to split."""
    texts = [(r.explanation or r.message).strip() for r in c.records]
    if len(c.records) < SEMANTIC_MIN or c.records[0].kind != "model" or len(set(texts)) < SEMANTIC_MIN:
        return [c]
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    X = np.asarray(embed(texts), dtype=float)
    labels = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                     distance_threshold=threshold).fit_predict(X)
    if len(set(labels)) == 1:
        return [c]
    parts = []
    for lab in sorted(set(labels)):
        idx = [i for i, x in enumerate(labels) if x == lab]
        recs = [c.records[i] for i in idx]
        # label = the member closest to the group centroid (a real explanation, not a made-up summary)
        centroid = X[idx].mean(axis=0)
        sims = X[idx] @ centroid / (np.linalg.norm(X[idx], axis=1) * np.linalg.norm(centroid) + 1e-9)
        rep = texts[idx[int(np.argmax(sims))]]
        sub = Cluster(f"{c.key}#{lab}", "semantic", c.check_id, c.category, _worst(recs),
                      f"{c.check_id}: {rep[:160]}", recs)
        sub.rate = round(c.rate * len({r.session_id for r in recs}) / max(c.n_sessions, 1), 3)
        parts.append(sub)
    return sorted(parts, key=lambda x: -len(x.records))


def cluster(fs: FailureSet, embed: Callable[[list[str]], list[list[float]]] | None = None) -> list[Cluster]:
    out = []
    for c in rule_clusters(fs):
        out += semantic_split(c, embed) if embed else [c]
    return sorted(out, key=lambda c: -c.impact)
