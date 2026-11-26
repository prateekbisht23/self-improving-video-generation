# Benchmark run c11acf32-candidate-hol

- agent `editing-agent-0.3+97e3caa31076` · evaluator `eval-1.2` · dataset `bench-v1-840ca30bb4` · splits ['holdout']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T08:41:09+00:00

| metric | value |
|---|---|
| tasks | 6 |
| completed | 6 |
| completion_rate | 1.0 |
| technical_valid_rate | 1.0 |
| mean_pass_rate | 0.848 |
| mean_actions | 9.0 |
| repairs_per_task | 2.67 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 100% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 83% |
| instruction.must_exclude | 100% |
| instruction.must_include | 0% |
| instruction.preference_satisfaction | 0% |
| narrative.structure | 17% |
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
| temporal.cut_through_word | 83% |
| temporal.dead_air | 83% |
| temporal.dialogue_continuity | 50% |
| temporal.repeated_footage | 100% |
| temporal.shot_durations | 50% |
| visual.framing | 67% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-05 | audio_captions | rendered | True | 0.909 | 23.567 | 1 | structure, dialogue_continuity |
| if-07 | instruction_following | rendered | True | 0.875 | 19.067 | 9 | must_include, shot_durations, framing |
| if-08 | instruction_following | rendered | True | 0.864 | 21.0 | 0 | must_include, structure, dialogue_continuity |
| pc-07 | pacing_scene_selection | rendered | True | 0.857 | 15.233 | 5 | adherence, structure, dialogue_continuity |
| ps-05 | personalization | rendered | True | 0.727 | 19.433 | 1 | preference_satisfaction, structure, cut_through_word, dead_air, shot_durations, framing |
| rs-05 | reference_style | rendered | True | 0.857 | 21.667 | 0 | structure, color_similarity, shot_durations |
