# 14 — The benchmark, splits, and LangSmith experiments

Code: `benchmarks/schemas/task.py`, `benchmarks/runner.py`, tasks in `benchmarks/{development,validation,holdout}/`, results in `benchmarks/results/`.

## 30 tasks, three splits (PRD §8)
| category | dev | val | holdout |
|---|---|---|---|
| instruction following | 5 | 1 | 2 |
| pacing & scene selection | 4 | 2 | 1 |
| reference style | 3 | 1 | 1 |
| audio & captions | 3 | 1 | 1 |
| personalization | 3 | 1 | 1 |
| **total** | **18** | **6** | **6** |

Each task has:
- source sample ids and an optional reference;
- instructions;
- creator preferences (personalization tasks);
- hard constraints: duration range, aspect ratio, captions required, phrases that must or must not be spoken;
- the checks it's mainly about.

The holdout tasks mostly use the two interviews (NIOSH, LibreOffice), so the final assessment includes *speakers and settings the improvement loop never tunes on*.

**Holdout isolation is enforced in code.** `load_tasks(["holdout"])` raises `HoldoutAccessError` unless `allow_holdout=True`. Holdout results go to their own file (`*-hol.json`), which Phase 5 must not read.

**Dataset version** = a content hash over every task file (`bench-v1-840ca30bb4`). Editing any task changes it, and every run records it alongside the agent version (with prompt hash), the evaluator version and the model ids.

## How a run is recorded
1. Each task runs end to end (editing session → render → independent evaluation) and is appended to `results/<run>.json` as it finishes. The run is resumable with `--resume`.
2. `results/<run>.md` is a human-readable table.
3. The tasks are upserted to the LangSmith dataset **`sivg-bench`** (inputs only, split as metadata). The results are logged as an **experiment** named after the agent version, with per-example feedback: `technical_gate`, `pass_rate`, `completed`, `repairs` and the judge scores. Two agent versions can then be compared side by side in the LangSmith *Compare experiments* view. Phase 5 depends on this.

## Baseline (agent `editing-agent-0.1+4a906df8ad8a`, evaluator `eval-1.0`, Gemini 3.5 Flash-Lite)
| metric | dev+val (24) | holdout (6) |
|---|---|---|
| completion rate | 95.8% | 83.3% |
| technical gate passed | 95.8% | 83.3% |
| mean check pass rate (uncalibrated) | 0.815 | 0.847 |
| actions per task | 9.4 | 6.8 |
| repairs per task | 2.35 | 0.2 |

Weakest checks (dev+val):

| check | pass rate | what it says about the agent |
|---|---|---|
| style.caption_match | 0% | always adds captions, even when the reference has none (the style guide only passes a caption *position*) |
| style.shot_length_similarity | 0% | reference medians are partly artefacts (each lightning flash counts as a "shot") |
| temporal.dialogue_continuity | 9% | clips start or end mid-sentence almost every time |
| narrative.structure | 13% | the judge rarely rates the story ≥ 3/5 on every dimension |
| temporal.cut_through_word | 48% | half the edits slice through a spoken word |

Two tasks failed to render (if-05, ac-05). Both ran out of repair budget on duration, and the deterministic fixup can only *shorten*. ac-05 also tripped the agent's own "most clips reuse the same scenes" rule, which is wrong for an interview made of two 50-second shots. These are concrete Phase 5 targets.

## Is the evaluator reproducible? Measured, not assumed
Re-evaluating the same 23 renders (`--reevaluate`) compared 510 check verdicts:

| | agreement |
|---|---|
| deterministic + signal checks | **100%** |
| model judges overall | 91.3% |
| `visual.framing` judge | 6 of 23 verdicts flipped (≈26%) |
| instruction / narrative judges | no flips |

Conclusions:
- The baseline is reproducible wherever it's deterministic.
- The framing judge is too noisy to gate on. Phase 5 should either ignore it for promotion decisions or use majority-of-3 voting.
- Agent variance (re-running the *agent*) is a separate question, handled with repeated runs in Phase 5 experiments.

## Known evaluator limitations (eval-1.0)
- `technical.black_frames` fires on legitimately dark footage (all 6 occurrences came from the night-time lightning b-roll). The fix is to compare with the source frames; doing that means a new evaluator version and a re-baseline.
- Caption WER compares ASR with ASR. It measures consistency, not truth.
- Style-shot similarity inherits shot-detector artefacts.

## Try this
1. Open the two experiments in LangSmith (Datasets → `sivg-bench` → Experiments) and sort by `pass_rate`.
2. `uv run python -m benchmarks.runner --split development --tasks if-01 --no-langsmith` runs one task.
3. Try `uv run python -c "from benchmarks.schemas.task import load_tasks; load_tasks('holdout')"` and read the error.
