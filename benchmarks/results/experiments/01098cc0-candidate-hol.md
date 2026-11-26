# Benchmark run 01098cc0-candidate-hol

- agent `editing-agent-0.3+20c1ce52b422` · evaluator `eval-1.3` · dataset `bench-v1-840ca30bb4` · splits ['holdout']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T13:57:31+00:00

| metric | value |
|---|---|
| tasks | 6 |
| completed | 5 |
| completion_rate | 0.833 |
| technical_valid_rate | 0.833 |
| mean_pass_rate | 0.829 |
| mean_actions | 7.6 |
| repairs_per_task | 1.6 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 67% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 60% |
| instruction.must_exclude | 100% |
| instruction.must_include | 100% |
| instruction.preference_satisfaction | 0% |
| narrative.structure | 20% |
| style.caption_match | 100% |
| style.color_similarity | 0% |
| style.shot_length_similarity | 100% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 100% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 100% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 60% |
| temporal.dead_air | 80% |
| temporal.dialogue_continuity | 60% |
| temporal.repeated_footage | 100% |
| temporal.shot_durations | 80% |
| visual.framing | 40% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-05 | audio_captions | rendered | True | 0.818 | 21.6 | 1 | accuracy, adherence, structure, dialogue_continuity |
| if-07 | instruction_following | rendered | True | 0.958 | 17.033 | 0 | framing |
| if-08 | instruction_following | failed |  |  |  | 14 |  |
| pc-07 | pacing_scene_selection | rendered | True | 0.833 | 19.167 | 2 | adherence, structure, dialogue_continuity |
| ps-05 | personalization | rendered | True | 0.773 | 25.0 | 4 | preference_satisfaction, structure, cut_through_word, dead_air, framing |
| rs-05 | reference_style | rendered | True | 0.762 | 22.233 | 1 | structure, color_similarity, cut_through_word, shot_durations, framing |
