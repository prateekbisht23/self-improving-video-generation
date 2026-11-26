# Experiment editing-agent-0.2+d43dbd596cae vs editing-agent-0.3+a8f89929be9d (rescore)

- experiment `25bed9cd-1096-4442-9c3b-1206bc08efee` · status **rejected**
- baseline `editing-agent-0.2+d43dbd596cae` → candidate `editing-agent-0.3+a8f89929be9d`
- dataset `bench-v1-840ca30bb4` · evaluator `eval-1.3` · splits ['development', 'validation'] · runs per version: 1
- models: judge=google_genai:gemini-3.5-flash-lite, planner=google_genai:gemini-3.5-flash-lite, improver=google_genai:gemini-3.5-flash-lite
- results: baseline `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/25bed9cd-baseline-dev-val.json`, candidate `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/25bed9cd-candidate-dev-val.json`

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
| mean_actions | 8.0 | 9.0 | 1.0 |
| mean_pass_rate | 0.824 | 0.822 | -0.002 |
| completion_rate | 0.958 | 0.958 | 0.0 |
| repairs_per_task | 1.57 | 2.48 | 0.91 |
| technical_valid_rate | 0.958 | 0.917 | -0.041 |

Paired per-task pass rate: mean Δ **-0.002** (95% bootstrap CI -0.098 … +0.099); wins 9 / ties 4 / losses 11.

| split | n | baseline | candidate | Δ |
|---|---|---|---|---|
| validation | 6 | 0.821 | 0.801 | -0.020 |
| development | 18 | 0.779 | 0.783 | +0.004 |

| check | baseline | candidate | Δ | n |
|---|---|---|---|---|
| captions.sync | 100% | 100% | +0% | 18 |
| visual.framing | 55% | 64% | +9% | 22 |
| captions.present | 100% | 100% | +0% | 9 |
| captions.accuracy | 96% | 89% | -7% | 18 |
| temporal.dead_air | 91% | 100% | +9% | 22 |
| technical.loudness | 100% | 100% | +0% | 22 |
| narrative.structure | 14% | 23% | +9% | 22 |
| style.caption_match ⬅ target | 0% | 100% | +100% | 4 |
| technical.file_valid | 100% | 100% | +0% | 22 |
| technical.resolution | 100% | 100% | +0% | 22 |
| instruction.adherence | 91% | 67% | -24% | 21 |
| style.color_similarity | 75% | 75% | +0% | 4 |
| technical.aspect_ratio | 100% | 100% | +0% | 22 |
| technical.black_frames | 86% | 86% | +0% | 22 |
| technical.audio_present | 100% | 100% | +0% | 22 |
| technical.frozen_frames | 100% | 100% | +0% | 22 |
| technical.missing_media | 100% | 100% | +0% | 22 |
| temporal.shot_durations | 55% | 55% | +0% | 22 |
| captions.speech_coverage | 100% | 100% | +0% | 18 |
| instruction.must_exclude | 100% | 100% | +0% | 1 |
| instruction.must_include | 100% | 86% | -14% | 7 |
| temporal.cut_through_word ⬅ target | 55% | 55% | +0% | 22 |
| temporal.repeated_footage | 91% | 86% | -4% | 22 |
| technical.duration_in_range | 100% | 100% | +0% | 22 |
| style.shot_length_similarity | 25% | 0% | -25% | 4 |
| temporal.dialogue_continuity | 23% | 18% | -4% | 22 |
| technical.av_stream_alignment | 100% | 100% | +0% | 22 |
| instruction.preference_satisfaction | 33% | 33% | +0% | 3 |

### Development + validation: in scope 'reference' (4 tasks: rs-01, rs-02, rs-03, rs-04)

Paired: mean Δ -0.024 (95% CI -0.038 … +0.000); wins 1 / ties 0 / losses 3.

| check | baseline | candidate | Δ | n |
|---|---|---|---|---|
| visual.framing | 25% | 50% | +25% | 4 |
| temporal.dead_air | 75% | 100% | +25% | 4 |
| style.caption_match ⬅ target | 0% | 100% | +100% | 4 |
| instruction.adherence | 100% | 50% | -50% | 4 |
| technical.black_frames | 100% | 50% | -50% | 4 |
| temporal.cut_through_word ⬅ target | 50% | 50% | +0% | 4 |
| style.shot_length_similarity | 25% | 0% | -25% | 4 |

(checks that did not change are omitted)

## Regression gates

**Eligible for promotion: NO**

Regressions:

- technical.black_frames: 100% -> 50% (n=4), p=0.017 vs A/A flip rate 11%

Improvements:

- target style.caption_match: 0% -> 100% (n=4), p=0.001 vs A/A flip rate 33%

Notes:

- failed the technical gate once, passed on the re-run (flaky, not gating): ['rs-01']
- scope 'reference': gates use the 4 in-scope tasks; the 20 others ran the baseline's code (A/A control). Control flips: {'captions.accuracy': '3/18', 'instruction.adherence': '5/17', 'narrative.structure': '6/18', 'technical.black_frames': '2/18', 'temporal.cut_through_word': '6/18', 'temporal.dead_air': '1/18', 'temporal.dialogue_continuity': '3/18', 'temporal.repeated_footage': '5/18', 'temporal.shot_durations': '2/18', 'visual.framing': '5/18', 'instruction.must_include': '1/7'}
- out-of-scope (noise by construction): render failures ['ps-02'], technical gate ['rs-01']
- instruction.adherence: 100% -> 50% (n=4): within A/A noise (p=0.106 vs A/A flip rate 29%); not gating
- style.shot_length_similarity: 25% -> 0% (n=4): 1 task flipped, below 2; not gating
- target temporal.cut_through_word: 50% -> 50% (n=4), p=1.000 vs A/A flip rate 33%
- validation mean 0.75 -> 0.714 on 1 in-scope task(s), below 3; not gating
- paired mean pass-rate difference -0.024 (95% CI (-0.0385, 0.0)): CI includes 0 on 4 in-scope tasks; not gating

Advisory (not gating): visual.framing
