# Experiment editing-agent-0.2+d43dbd596cae vs editing-agent-0.3+20c1ce52b422

- experiment `01098cc0-899e-4d1f-b2f8-53258ae734d3` · status **promoted**
- baseline `editing-agent-0.2+d43dbd596cae` → candidate `editing-agent-0.3+20c1ce52b422`
- dataset `bench-v1-840ca30bb4` · evaluator `eval-1.3` · splits ['development', 'validation'] · runs per version: 1
- models: judge=google_genai:gemini-3.5-flash-lite, planner=google_genai:gemini-3.5-flash-lite, improver=google_genai:gemini-3.5-flash-lite
- results: baseline `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/01098cc0-baseline-dev-val.json`, candidate `/Users/prateekbisht/Projects/self-improving-video-generation/benchmarks/results/experiments/01098cc0-candidate-dev-val.json`

## Why this candidate

**Hypothesis:** If captions follow the reference (dropped when the reference has none and nobody asked) and clip edges move off dips to black wherever captions were dropped, style.caption_match improves without exposing black frames the captions used to cover

**Targets:** style.caption_match

**Policy changes:** `{'trim_black': 'when_captions_skipped', 'captions_follow_reference': True}`

**Expected effect:** caption_match 0->100% on reference tasks; black_frames no worse than baseline

**Risks:** trimming black shortens clips (duration repairs); sub-second dark lightning clips are left as they are

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
| mean_actions | 8.0 | 8.9 | 0.9 |
| mean_pass_rate | 0.824 | 0.819 | -0.005 |
| completion_rate | 0.958 | 0.875 | -0.083 |
| repairs_per_task | 1.39 | 2.38 | 0.99 |
| technical_valid_rate | 0.958 | 0.875 | -0.083 |

Paired per-task pass rate: mean Δ **-0.072** (95% bootstrap CI -0.186 … +0.009); wins 8 / ties 7 / losses 9.

| split | n | baseline | candidate | Δ |
|---|---|---|---|---|
| validation | 6 | 0.678 | 0.685 | +0.007 |
| development | 18 | 0.827 | 0.727 | -0.099 |

| check | baseline | candidate | Δ | n |
|---|---|---|---|---|
| captions.sync | 100% | 100% | +0% | 17 |
| visual.framing | 81% | 71% | -10% | 21 |
| captions.present | 100% | 100% | +0% | 7 |
| captions.accuracy | 100% | 100% | +0% | 17 |
| temporal.dead_air | 95% | 95% | +0% | 21 |
| technical.loudness | 100% | 100% | +0% | 21 |
| narrative.structure | 5% | 5% | +0% | 21 |
| style.caption_match ⬅ target | 0% | 100% | +100% | 4 |
| technical.file_valid | 100% | 100% | +0% | 21 |
| technical.resolution | 100% | 100% | +0% | 21 |
| instruction.adherence | 71% | 80% | +9% | 20 |
| style.color_similarity | 50% | 50% | +0% | 4 |
| technical.aspect_ratio | 100% | 100% | +0% | 21 |
| technical.black_frames | 86% | 86% | +0% | 21 |
| technical.audio_present | 100% | 100% | +0% | 21 |
| technical.frozen_frames | 100% | 100% | +0% | 21 |
| technical.missing_media | 100% | 100% | +0% | 21 |
| temporal.shot_durations | 57% | 67% | +10% | 21 |
| captions.speech_coverage | 100% | 100% | +0% | 17 |
| instruction.must_include | 100% | 80% | -20% | 5 |
| temporal.cut_through_word | 43% | 52% | +10% | 21 |
| temporal.repeated_footage | 95% | 90% | -5% | 21 |
| technical.duration_in_range | 100% | 100% | +0% | 21 |
| style.shot_length_similarity | 0% | 25% | +25% | 4 |
| temporal.dialogue_continuity | 19% | 5% | -14% | 21 |
| technical.av_stream_alignment | 100% | 100% | +0% | 21 |
| instruction.preference_satisfaction | 50% | 25% | -25% | 4 |

### Development + validation: in scope 'reference' (4 tasks: rs-01, rs-02, rs-03, rs-04)

Paired: mean Δ -0.022 (95% CI -0.081 … +0.036); wins 2 / ties 0 / losses 2.

| check | baseline | candidate | Δ | n |
|---|---|---|---|---|
| visual.framing | 100% | 50% | -50% | 4 |
| style.caption_match ⬅ target | 0% | 100% | +100% | 4 |
| instruction.adherence | 75% | 50% | -25% | 4 |
| technical.black_frames | 75% | 100% | +25% | 4 |
| temporal.shot_durations | 50% | 75% | +25% | 4 |
| temporal.cut_through_word | 75% | 25% | -50% | 4 |
| temporal.repeated_footage | 100% | 75% | -25% | 4 |
| style.shot_length_similarity | 0% | 25% | +25% | 4 |

(checks that did not change are omitted)

## Regression gates

**Eligible for promotion: YES**

Improvements:

- target style.caption_match: 0% -> 100% (n=4), p=0.000 vs A/A flip rate 24%

Notes:

- scope 'reference': gates use the 4 in-scope tasks; the 20 others ran the baseline's code (A/A control). Control flips: {'instruction.adherence': '3/16', 'technical.black_frames': '3/17', 'temporal.cut_through_word': '4/17', 'temporal.dialogue_continuity': '3/17', 'temporal.repeated_footage': '2/17', 'temporal.shot_durations': '3/17', 'visual.framing': '4/17', 'instruction.must_include': '1/5', 'instruction.preference_satisfaction': '1/4'}
- out-of-scope (noise by construction): render failures ['if-02', 'if-05'], technical gate []
- instruction.adherence: 75% -> 50% (n=4): 1 task flipped, below 2; not gating
- temporal.cut_through_word: 75% -> 25% (n=4): within A/A noise (p=0.071 vs A/A flip rate 24%); not gating
- temporal.repeated_footage: 100% -> 75% (n=4): 1 task flipped, below 2; not gating
- visual.framing: 100% -> 50% (n=4): within A/A noise (p=0.071 vs A/A flip rate 24%); not gating
- paired mean pass-rate difference -0.022 (95% CI (-0.0805, 0.036)): CI includes 0 on 4 in-scope tasks; not gating

Advisory (not gating): visual.framing

## Holdout assessment (independent; never seen by diagnosis or candidate generation)

| metric | baseline | candidate | Δ |
|---|---|---|---|
| mean_actions | 6.8 | 7.6 | 0.8 |
| mean_pass_rate | 0.851 | 0.829 | -0.022 |
| completion_rate | 1.0 | 0.833 | -0.167 |
| repairs_per_task | 0.83 | 1.6 | 0.77 |
| technical_valid_rate | 1.0 | 0.833 | -0.167 |

Paired: mean Δ -0.160 (95% CI -0.465 … +0.006); wins 2 / ties 1 / losses 3.

| check | baseline | candidate | n |
|---|---|---|---|
| visual.framing | 60% | 40% | 5 |
| style.caption_match | 0% | 100% | 1 |
| instruction.adherence | 80% | 60% | 5 |

### Holdout: in scope 'reference' (1 tasks: rs-05)

Paired: mean Δ +0.012 (95% CI +0.012 … +0.012); wins 1 / ties 0 / losses 0.

| check | baseline | candidate | Δ | n |
|---|---|---|---|---|
| visual.framing | 100% | 0% | -100% | 1 |
| style.caption_match ⬅ target | 0% | 100% | +100% | 1 |
| temporal.dialogue_continuity | 0% | 100% | +100% | 1 |

(checks that did not change are omitted)

## Decision

promoted by **prateek** at 2026-11-26 15:49:57.976802+00:00: caption fix + black trim; holdout rs-05 improved; if-08 miss is out-of-scope baseline noise
