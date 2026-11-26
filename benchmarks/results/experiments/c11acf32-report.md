# Experiment editing-agent-0.2+d43dbd596cae vs editing-agent-0.3+97e3caa31076 (rescore)

- experiment `c11acf32-9a5a-4b71-afcd-e135f3e49284` · status **declined**
- baseline `editing-agent-0.2+d43dbd596cae` → candidate `editing-agent-0.3+97e3caa31076`
- dataset `bench-v1-840ca30bb4` · evaluator `eval-1.2` · splits ['development', 'validation'] · runs per version: 1
- models: judge=google_genai:gemini-3.5-flash-lite, planner=google_genai:gemini-3.5-flash-lite, improver=google_genai:gemini-3.5-flash-lite
- results: baseline `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/c11acf32-baseline-dev-val.json`, candidate `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/c11acf32-candidate-dev-val.json`

## Why this candidate

**Hypothesis:** If we enable captions_follow_reference and set snap_cuts to word, then style.caption_match and temporal.cut_through_word improve because captions will match reference videos and clip boundaries will safely align to word gaps without causing sentence-snapping rendering failures.

**Targets:** style.caption_match, temporal.cut_through_word

**Policy changes:** `{'snap_cuts': 'word', 'captions_follow_reference': True}`

**Expected effect:** style.caption_match reaches 100% pass rate when reference videos have no captions, and temporal.cut_through_word improves without causing the duration failures seen when using sentence-level snapping.

**Risks:** Minor regressions in technical metrics could occur if reference video matching introduces unexpected edge cases, but word-level snapping avoids the aggressive shifts that previously broke target durations.

## Failure patterns it was derived from (development split)

| cluster | renders affected | severity | tasks | root cause (top) |
|---|---|---|---|---|
| narrative.structure fails | 78% | major | 14 | Improper clip boundaries and aggressive trimming cause sentences to cut off mid-thought, destroying the narrative ending. (high) |
| instruction.preference_satisfaction fails | 67% | major | 2 | The agent fails to apply or select a warm color grade matching user preference in task ps-01. (high) |
| temporal.cut_through_word fails | 56% | major | 10 | The agent selects clip in-points and out-points based on arbitrary timestamps rather than aligning them to phonetic or word boundaries, resu (high) |
| style.caption_match fails | 100% | minor | 3 | The planning policy defaults to enabling captions (plan_added_captions: true) even when instructions do not mention captions and reference v (high) |
| style.shot_length_similarity fails | 100% | minor | 3 | The agent plans and executes clips with median shot lengths that diverge significantly from the reference video's target pacing (e.g. median (high) |

## Results: development + validation

| metric | baseline | candidate | Δ |
|---|---|---|---|
| mean_actions | 8.9 | 9.0 | 0.1 |
| mean_pass_rate | 0.812 | 0.838 | 0.026 |
| completion_rate | 0.917 | 0.958 | 0.041 |
| repairs_per_task | 2.14 | 2.57 | 0.43 |
| technical_valid_rate | 0.917 | 0.958 | 0.041 |

Paired per-task pass rate: mean Δ **+0.059** (95% bootstrap CI -0.054 … +0.174); wins 13 / ties 4 / losses 7.

| split | n | baseline | candidate | Δ |
|---|---|---|---|---|
| validation | 6 | 0.657 | 0.831 | +0.174 |
| development | 18 | 0.774 | 0.794 | +0.020 |

| check | baseline | candidate | Δ | n |
|---|---|---|---|---|
| captions.sync | 100% | 100% | +0% | 17 |
| visual.framing | 76% | 81% | +5% | 21 |
| captions.present | 100% | 100% | +0% | 7 |
| captions.accuracy | 76% | 88% | +12% | 17 |
| temporal.dead_air | 95% | 95% | +0% | 21 |
| technical.loudness | 100% | 100% | +0% | 21 |
| narrative.structure | 19% | 29% | +10% | 21 |
| style.caption_match ⬅ target | 0% | 100% | +100% | 4 |
| technical.file_valid | 100% | 100% | +0% | 21 |
| technical.resolution | 100% | 100% | +0% | 21 |
| instruction.adherence | 67% | 85% | +18% | 20 |
| style.color_similarity | 50% | 75% | +25% | 4 |
| technical.aspect_ratio | 100% | 100% | +0% | 21 |
| technical.black_frames | 90% | 86% | -5% | 21 |
| technical.audio_present | 100% | 100% | +0% | 21 |
| technical.frozen_frames | 100% | 100% | +0% | 21 |
| technical.missing_media | 100% | 100% | +0% | 21 |
| temporal.shot_durations | 62% | 52% | -10% | 21 |
| captions.speech_coverage | 100% | 100% | +0% | 17 |
| instruction.must_exclude | 100% | 100% | +0% | 1 |
| instruction.must_include | 100% | 100% | +0% | 7 |
| temporal.cut_through_word ⬅ target | 43% | 76% | +33% | 21 |
| temporal.repeated_footage | 90% | 90% | +0% | 21 |
| technical.duration_in_range | 100% | 100% | +0% | 21 |
| style.shot_length_similarity | 0% | 0% | +0% | 4 |
| temporal.dialogue_continuity | 14% | 14% | +0% | 21 |
| technical.av_stream_alignment | 100% | 100% | +0% | 21 |
| instruction.preference_satisfaction | 25% | 25% | +0% | 4 |

## Regression gates

**Eligible for promotion: YES**

Improvements:

- target style.caption_match: 0% -> 100% (n=4)
- target temporal.cut_through_word: 43% -> 76% (n=21)

Notes:

- failed once, rendered on the re-run (flaky, not gating): ['pc-02']

Advisory (not gating): visual.framing

## Holdout assessment (independent; never seen by diagnosis or candidate generation)

| metric | baseline | candidate | Δ |
|---|---|---|---|
| mean_actions | 7.2 | 9.0 | 1.8 |
| mean_pass_rate | 0.861 | 0.848 | -0.013 |
| completion_rate | 1.0 | 1.0 | 0.0 |
| repairs_per_task | 0.5 | 2.67 | 2.17 |
| technical_valid_rate | 1.0 | 1.0 | 0.0 |

Paired: mean Δ -0.013 (95% CI -0.065 … +0.027); wins 3 / ties 1 / losses 2.

| check | baseline | candidate | n |
|---|---|---|---|
| style.caption_match | 0% | 100% | 1 |
| temporal.shot_durations | 83% | 50% | 6 |
| instruction.must_include | 50% | 0% | 2 |
| temporal.cut_through_word | 83% | 83% | 6 |

## Decision

declined by **prateek** at 2026-11-26 10:26:14.616329+00:00: holdout flat; shot_durations cost repeated
