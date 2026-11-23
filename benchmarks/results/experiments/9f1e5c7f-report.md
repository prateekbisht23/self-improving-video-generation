# Experiment editing-agent-0.2+d43dbd596cae vs editing-agent-0.3+a8f89929be9d

- experiment `9f1e5c7f-043b-42fb-91b2-1805170c786d` · status **rejected**
- baseline `editing-agent-0.2+d43dbd596cae` → candidate `editing-agent-0.3+a8f89929be9d`
- dataset `bench-v1-840ca30bb4` · evaluator `eval-1.1` · splits ['development', 'validation'] · runs per version: 1
- models: judge=google_genai:gemini-3.5-flash-lite, planner=google_genai:gemini-3.5-flash-lite, improver=google_genai:gemini-3.5-flash-lite
- results: baseline `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/9f1e5c7f-baseline-dev-val.json`, candidate `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/9f1e5c7f-candidate-dev-val.json`

## Why this candidate

**Hypothesis:** if we enable captions_follow_reference and set snap_cuts to word with snap_repairs to word, check style.caption_match and temporal.cut_through_word improve because captions will align with the reference and cuts will avoid mid-word truncations without breaking target duration constraints caused by aggressive sentence shifting.

**Targets:** style.caption_match, temporal.cut_through_word

**Policy changes:** `{'captions_follow_reference': True}`

**Expected effect:** Style caption match failures on reference tasks will be resolved by automatically skipping captions when absent in the reference video, and word-level cut snapping will prevent truncated words without causing severe duration shifts that broke rendering tasks in previous experiments.

**Risks:** Sentence boundaries might be preferred by narrative structure, but word-level snapping avoids the large duration shifts that caused tasks pc-02 and pc-06 to fail rendering.

## Failure patterns it was derived from (development split)

| cluster | renders affected | severity | tasks | root cause (top) |
|---|---|---|---|---|
| narrative.structure fails | 88% | major | 15 | The agent stitches together short clip segments from disparate timestamps (e.g., in ac-03, selecting clips starting at 18.63, 22.27, and 27. (high) |
| instruction.preference_satisfaction fails | 67% | major | 2 | The agent fails to apply the requested warm color look preference in task ps-01, resulting in a cool purple/blue background tone. (high) |
| temporal.cut_through_word fails | 53% | major | 9 | The planner selects clip boundary timestamps without forcing them to align to word or sentence boundaries, leading to mid-word cuts across t (high) |
| style.caption_match fails | 100% | minor | 3 | The agent's planner defaults to enabling captions (captions: true) regardless of whether the reference video contains captions. (high) |
| style.shot_length_similarity fails | 100% | minor | 3 | The agent fails to match reference shot length pacing during initial planning, resulting in median shot durations that are either too long o (high) |

## Results: development + validation

| metric | baseline | candidate | Δ |
|---|---|---|---|
| mean_actions | 8.7 | 8.9 | 0.2 |
| mean_pass_rate | 0.818 | 0.808 | -0.01 |
| completion_rate | 0.958 | 1.0 | 0.042 |
| repairs_per_task | 1.91 | 2.42 | 0.51 |
| technical_valid_rate | 0.958 | 1.0 | 0.042 |

Paired per-task pass rate: mean Δ **+0.024** (95% bootstrap CI -0.035 … +0.108); wins 8 / ties 7 / losses 9.

| split | n | baseline | candidate | Δ |
|---|---|---|---|---|
| validation | 6 | 0.672 | 0.83 | +0.158 |
| development | 18 | 0.822 | 0.8 | -0.021 |

| check | baseline | candidate | Δ | n |
|---|---|---|---|---|
| captions.sync | 100% | 100% | +0% | 19 |
| visual.framing | 61% | 52% | -9% | 23 |
| captions.present | 100% | 100% | +0% | 9 |
| captions.accuracy | 91% | 95% | +3% | 19 |
| temporal.dead_air | 100% | 100% | +0% | 23 |
| technical.loudness | 100% | 100% | +0% | 23 |
| narrative.structure | 17% | 14% | -4% | 22 |
| style.caption_match ⬅ target | 0% | 100% | +100% | 4 |
| technical.file_valid | 100% | 100% | +0% | 23 |
| technical.resolution | 100% | 100% | +0% | 23 |
| instruction.adherence | 78% | 74% | -4% | 23 |
| style.color_similarity | 25% | 50% | +25% | 4 |
| technical.aspect_ratio | 100% | 100% | +0% | 23 |
| technical.black_frames | 91% | 78% | -13% | 23 |
| technical.audio_present | 100% | 100% | +0% | 23 |
| technical.frozen_frames | 100% | 91% | -9% | 23 |
| technical.missing_media | 100% | 100% | +0% | 23 |
| temporal.shot_durations | 48% | 61% | +13% | 23 |
| captions.speech_coverage | 100% | 100% | +0% | 19 |
| instruction.must_exclude | 100% | 100% | +0% | 1 |
| instruction.must_include | 100% | 100% | +0% | 6 |
| temporal.cut_through_word ⬅ target | 52% | 65% | +13% | 23 |
| temporal.repeated_footage | 100% | 74% | -26% | 23 |
| technical.duration_in_range | 100% | 100% | +0% | 23 |
| style.shot_length_similarity | 0% | 0% | +0% | 4 |
| temporal.dialogue_continuity | 13% | 9% | -4% | 23 |
| technical.av_stream_alignment | 100% | 100% | +0% | 23 |
| instruction.preference_satisfaction | 25% | 25% | +0% | 4 |

## Regression gates

**Eligible for promotion: NO**

Regressions:

- technical.black_frames: 91% -> 78% (n=23)
- temporal.repeated_footage: 100% -> 74% (n=23)

Improvements:

- target style.caption_match: 0% -> 100% (n=4)
- target temporal.cut_through_word: 52% -> 65% (n=23)

Advisory (not gating): visual.framing
