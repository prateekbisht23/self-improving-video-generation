# 18 — Failure diagnosis: from evaluation issues to root causes

PRD FR-11: find recurring failures, group them, retrieve the runs behind them, explain them with evidence. Code: `improvement/collection.py`, `improvement/clustering/`, `improvement/diagnosis/`.

## 1. Collection: which data the improvement loop may see
`collect(s, agent_version)` gathers every failed check (`evaluation_issues`) of one agent version, plus the sessions that never rendered.
- **Development split only.** Validation is for choosing between versions, and holdout is for the final independent estimate. If the loop diagnosed on validation, it would tune to the very tasks it's later judged on. Passing any other split raises `HoldoutAccessError`. A test also scans `improvement/` with the AST and fails if anything other than `experiments/holdout.py` mentions holdout.
- **One render per task.** A resumed run can leave several sessions for the same task and version; only the latest counts.
- An unrendered session becomes a synthetic `agent.no_render` failure, with its error normalised ("duration outside target"). Edits that never rendered are the most important failures, and they have no evaluation.

## 2. Clustering: rules first, embeddings where they help
```
uv run python -m improvement.cli analyze      # no model calls
```
Clusters for v0.2 on the 18 development tasks:

| impact | renders affected | cluster |
|---|---|---|
| 1.89 | 94% | narrative.structure (major) |
| 1.00 | 100% (3 of 3 tasks with a reference) | style.caption_match |
| 1.00 | 100% | style.shot_length_similarity |
| 0.89 | 89% | temporal.dialogue_continuity |
| 0.89 | 44% | temporal.cut_through_word (major) |
| 0.67 | 33% | instruction.adherence (major) |
| … | | |

- **Rule clusters**: one per failed check id. The evaluator already defines a precise category for each failure, so this is exact and free.
- **Semantic sub-clusters**: model-judge failures share a check id but fail for different reasons ("weak hook" vs "abrupt ending"). Their free-text explanations are embedded (`gemini-embedding-001`) and grouped with `AgglomerativeClustering(metric="cosine", linkage="average", distance_threshold=0.35)`. We don't pick k up front; the threshold decides how many groups there are. Each sub-cluster is labelled with its member closest to the centroid: a real explanation, not a generated summary. Template messages from deterministic checks ("2 clip(s) start mid-sentence") gain nothing from embeddings and stay as rule clusters.
- **Impact** = severity weight (critical 4, major 2, minor 1) × share of renders affected. A frequent minor problem and a rarer major one can rank about the same, which is intended.
- **Noisy checks are excluded from optimisation.** `visual.framing` flipped on 6 of 23 re-evaluations of identical renders (note 14), so the loop doesn't chase it. Otherwise it could "improve" a coin flip.

## 3. Diagnosis: evidence first, model second
`gather_evidence` is deterministic. For each top cluster it pulls sample sessions (instructions, plan, final clips, every action with its errors, repair count, LangSmith `trace_id`) and runs **probes** that test common hypotheses:

| probe | question | v0.2 answer |
|---|---|---|
| `edge_origin` | were the bad cut points chosen by the planner, or introduced by repairs? | dialogue_continuity: **39 of 44** bad edges came straight from the plan; cut_through_word: 14 of 21 |
| `captions` | did the plan add captions although the reference has none and nobody asked? | rs-01, rs-02, rs-03: **yes, all three** |
| duration probe | estimated vs actual planned seconds vs target | planner arithmetic errors visible per task |
| `counterfactual_snap_replay` | what would cut snapping have done to *these* timelines? | see below |

Only then does the model (`MODEL_IMPROVER`, defaulting to the planner model) read that evidence. It returns a `Diagnosis`: root causes that must cite the evidence, a confidence for each, and fix directions. The prompt allows "the check itself is wrong" as an answer (e.g. black-frame flags on night-time lightning footage). The model explains failures; it never writes code.

### Counterfactual replay: test a knob before spending quota
Some knobs act deterministically on recorded data. Snapping clip edges to speech boundaries is one: apply it to the final timelines we already have, then re-score them with the evaluator's own check functions. This needs no rendering and no model calls. First, a sanity check that the replay is faithful: with snapping `off` it reproduces the measured baseline exactly (13% / 52% on dev+val).

All 23 rendered dev+val edits:

| policy | dialogue_continuity | cut_through_word | mean duration change |
|---|---|---|---|
| off (v0.2) | 13% | 52% | 0 |
| word gaps | 9% | 87% | +0.5 s |
| sentence, max shift 2 s | 17% | 87% | +1.2 s |
| sentence, max shift 5 s | 35% | 91% | +2.1 s |

The first version of sentence snapping (unlimited shift) added **+6.4 s** per edit, enough to push edits out of their duration window. That's why `snap_max_shift` exists. The replay also explains *why* dialogue continuity is so hard here: sentences in these sources average 4–17 s, but shots are around 4 s, and the check requires every clip edge to sit on a sentence boundary. Snapping can't fully solve that; only a planner that picks whole sentences can, at a cost in pacing.

The replay is an estimate. In a real run the agent reacts to the changed durations (repairs, fixup). So it informs the proposal, and the experiment decides.

## Gotchas we hit
- Alembic autogenerate tried to **drop LangGraph's checkpoint tables**, because it sees tables it doesn't manage as "removed". `include_object` in `db/migrations/env.py` now excludes `checkpoint*`.
- The holdout-isolation test failed on its first run because `graph.py` used `"holdout"` as a node name. We renamed the node (`final_assessment`) rather than weakening the test.

## Try this
1. `uv run python -m improvement.cli analyze`. Which cluster would you fix first, and does impact agree with you?
2. Add a probe for `narrative.structure`, for example the position of the clip the planner labelled "hook" and whether the last clip ends a sentence. Does the judge's explanation match the measurement?
3. Lower `SEMANTIC_THRESHOLD` to 0.2 and re-cluster the judge failures. When do the clusters stop being meaningful?
