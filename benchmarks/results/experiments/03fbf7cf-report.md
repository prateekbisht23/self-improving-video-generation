# Experiment editing-agent-0.2+d43dbd596cae vs editing-agent-0.3+97e3caa31076

- experiment `03fbf7cf-b7be-4679-8242-7cce3288fea9` · status **rejected**
- baseline `editing-agent-0.2+d43dbd596cae` → candidate `editing-agent-0.3+97e3caa31076`
- dataset `bench-v1-840ca30bb4` · evaluator `eval-1.1` · splits ['development', 'validation'] · runs per version: 1
- models: judge=google_genai:gemini-3.5-flash-lite, planner=google_genai:gemini-3.5-flash-lite, improver=google_genai:gemini-3.5-flash-lite
- results: baseline `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/03fbf7cf-baseline-dev-val.json`, candidate `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/03fbf7cf-candidate-dev-val.json`

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
| mean_actions | 8.0 | 7.3 | -0.7 |
| mean_pass_rate | 0.831 | 0.819 | -0.012 |
| completion_rate | 0.917 | 0.917 | 0.0 |
| repairs_per_task | 1.59 | 1.0 | -0.59 |
| technical_valid_rate | 0.917 | 0.917 | 0.0 |

Paired per-task pass rate: mean Δ **-0.011** (95% bootstrap CI -0.147 … +0.122); wins 9 / ties 4 / losses 11.

| split | n | baseline | candidate | Δ |
|---|---|---|---|---|
| validation | 6 | 0.705 | 0.8 | +0.096 |
| development | 18 | 0.781 | 0.734 | -0.047 |

| check | baseline | candidate | Δ | n |
|---|---|---|---|---|
| captions.sync | 100% | 100% | +0% | 17 |
| visual.framing | 65% | 60% | -5% | 20 |
| captions.present | 100% | 100% | +0% | 9 |
| captions.accuracy | 100% | 94% | -6% | 17 |
| temporal.dead_air | 95% | 95% | +0% | 20 |
| technical.loudness | 100% | 100% | +0% | 20 |
| narrative.structure | 20% | 15% | -5% | 20 |
| style.caption_match ⬅ target | 0% | 100% | +100% | 3 |
| technical.file_valid | 100% | 100% | +0% | 20 |
| technical.resolution | 100% | 100% | +0% | 20 |
| instruction.adherence | 75% | 75% | +0% | 20 |
| style.color_similarity | 100% | 67% | -33% | 3 |
| technical.aspect_ratio | 100% | 100% | +0% | 20 |
| technical.black_frames | 85% | 75% | -10% | 20 |
| technical.audio_present | 100% | 100% | +0% | 20 |
| technical.frozen_frames | 100% | 95% | -5% | 20 |
| technical.missing_media | 100% | 100% | +0% | 20 |
| temporal.shot_durations | 65% | 45% | -20% | 20 |
| captions.speech_coverage | 100% | 100% | +0% | 17 |
| instruction.must_include | 100% | 100% | +0% | 6 |
| temporal.cut_through_word ⬅ target | 60% | 75% | +15% | 20 |
| temporal.repeated_footage | 95% | 100% | +5% | 20 |
| technical.duration_in_range | 100% | 100% | +0% | 20 |
| style.shot_length_similarity | 0% | 0% | +0% | 3 |
| temporal.dialogue_continuity | 5% | 5% | +0% | 20 |
| technical.av_stream_alignment | 100% | 100% | +0% | 20 |
| instruction.preference_satisfaction | 25% | 50% | +25% | 4 |

## Regression gates

**Eligible for promotion: NO**

Critical:

- tasks no longer render: ['pc-02', 'pc-03']

Regressions:

- style.color_similarity: 100% -> 67% (n=3)
- temporal.shot_durations: 65% -> 45% (n=20)
- paired mean pass-rate difference -0.011 (95% CI (-0.147, 0.1224))

Improvements:

- target style.caption_match: 0% -> 100% (n=3)
- target temporal.cut_through_word: 60% -> 75% (n=20)

Advisory (not gating): visual.framing
