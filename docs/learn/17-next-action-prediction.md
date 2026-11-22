# 17 — Next-action prediction: four predictors and an honest comparison

PRD FR-07: given the current editing state, predict the agent's next operation. We use it two ways:
- **online**: before every action, the editing graph logs the rules predictor's guess (`action_predictions`, `mode='online'`). This costs nothing and gives a live accuracy signal.
- **offline**: `uv run python -m agent.prediction.evaluate` compares all predictors on every logged action. Results go to `benchmarks/results/prediction-*.json` and to `action_predictions` (`mode='offline'`).

## One featurizer, four predictors
`agent/prediction/features.py::featurize(timeline, history, instructions, min, max, memory)` turns a state into a flat dict:
- timeline facts: duration under/in/over the target, clip count, captions/title/transition/colour present;
- history: last two actions, whether the last one succeeded and where it came from (plan/repair/fixup), whether a style was applied, step number;
- wants, from instruction and memory keywords: captions, title, transitions, colour, all caps.

Every predictor takes that same dict, so the comparison is fair.

| predictor | how it works | cost |
|---|---|---|
| `rules-v1` | hand-written: "no clips → select_clip; too long → trim_clip; captions wanted but missing → generate_captions; ..." | free, µs |
| `markov-1` | counts P(next ∣ last action) from training sessions | free, µs |
| `learned-logreg` | sklearn `DictVectorizer` + `LogisticRegression` on all features | free, ~0.1 ms |
| `llm:<planner>` | asks the planner model for the 3 most likely ops (structured output, validated against the action space) | 1 API call, ~4.5 s |

## Evaluation protocol (the part that's easy to get wrong)
- **Group by session.** Consecutive steps of one session are almost identical, so a random row split leaks: the model sees step 5 in training and is tested on step 6. We use `GroupKFold(5)` on the session id.
- **Holdout benchmark sessions are excluded entirely** (`build_dataset` drops any session whose `benchmark_task` isn't in development/validation). The predictors never see them, not even to train.
- **The validation split** trains on non-validation sessions and tests on the validation benchmark sessions. This is the only protocol where the LLM runs, because of its cost.
- **Errors are not wrong answers.** When the API fails (quota), the prediction is `None`. It's reported as `errors`/`coverage` and left out of accuracy. The first run scored the LLM 0.0 because all its calls hit the daily quota, which measured our quota, not the model.
- **Baseline to beat:** always guessing the most common label (`select_clip`).

## Results (485 actions, 54 sessions; majority-class baseline 0.505)

5-fold CV grouped by session:

| predictor | top-1 | top-3 |
|---|---|---|
| rules-v1 | 0.608 | 0.909 |
| markov-1 | 0.722 | 0.953 |
| learned-logreg | **0.788** | **0.967** |

Validation split (train 380 actions / 42 sessions, test 105 / 12):

| predictor | top-1 | top-3 | plan steps | repair steps | p50 latency |
|---|---|---|---|---|---|
| rules-v1 | 0.600 | 0.905 | 0.64 | 0.50 | <0.1 ms |
| markov-1 | 0.743 | 0.971 | 0.83 | 0.59 | <0.1 ms |
| learned-logreg | **0.800** | **0.990** | 0.87 | 0.68 | 0.1 ms |
| llm (Gemini 3.5 Flash-Lite) | 0.276 | 0.467 | 0.39 | 0.06 | 4.5 s |

The LLM had full coverage (0 errors) and 98% valid names, so its low score is real.

## What the numbers say
- **A 0.1 ms logistic regression beats a 4.5 s LLM by about 50 points.** The LLM knows what video editing usually looks like. The classifier knows what *this* agent does: it executes a plan in a fixed order, and it repairs with particular operations. Prediction is about the agent's habits, which only the logs contain.
- **Plan steps are easy and repair steps are hard.** Everyone does well on planned steps (0.64–0.87). Repairs depend on which check failed, and that isn't in the features yet. Adding "last evaluation problem" as a feature is the obvious next step.
- **Top-3 is almost solved** (0.99 for the classifier). A UI can show three suggestions and nearly always include the right one.
- **Markov already gets most of the gain.** "What came after the last action" alone gives 0.72–0.74. The other features add another 6 points.

## Gotchas we hit
- Free-tier quota (500 requests/day per model) ran out mid-evaluation. Hence the `None` → coverage handling, and the runner stops at the first `PerDay` error so a run can be resumed instead of filling up with errors.
- Labels change when the agent changes. A predictor trained on agent v0.1 logs predicts v0.1's habits. The learned predictor is versioned by a hash of its training data (`learned-logreg-9cbc4446`) and should be retrained after a Phase 5 promotion.

## Try this
1. `uv run python -m agent.prediction.evaluate --no-llm` takes seconds. Open the JSON and compare `top1_by_stage` across predictors.
2. Add a feature `last_problem` (the first problem string from the last failed action, bucketed: duration/captions/style/...) and re-run. Does repair-step accuracy move?
3. Online accuracy: `SELECT predictor, avg(correct_top1::int) FROM action_predictions WHERE mode='online' GROUP BY 1;`
4. Swap `LogisticRegression` for `RandomForestClassifier` in `predictors.py`. With ~500 rows, does it overfit (CV vs validation gap)?
