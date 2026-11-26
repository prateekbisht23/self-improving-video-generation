# Benchmark run 01098cc0-candidate-dev-val

- agent `editing-agent-0.3+20c1ce52b422` · evaluator `eval-1.3` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T13:18:17+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 21 |
| completion_rate | 0.875 |
| technical_valid_rate | 0.875 |
| mean_pass_rate | 0.819 |
| mean_actions | 8.9 |
| repairs_per_task | 2.38 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 100% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 80% |
| instruction.must_include | 80% |
| instruction.preference_satisfaction | 25% |
| narrative.structure | 5% |
| style.caption_match | 100% |
| style.color_similarity | 50% |
| style.shot_length_similarity | 25% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 86% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 100% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 52% |
| temporal.dead_air | 95% |
| temporal.dialogue_continuity | 5% |
| temporal.repeated_footage | 90% |
| temporal.shot_durations | 67% |
| visual.framing | 71% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.909 | 23.267 | 0 | structure, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.909 | 17.067 | 0 | structure, dialogue_continuity |
| ac-03 | audio_captions | rendered | True | 0.773 | 24.6 | 2 | structure, black_frames, cut_through_word, dialogue_continuity, framing |
| if-01 | instruction_following | rendered | True | 0.87 | 22.7 | 1 | structure, dialogue_continuity, shot_durations |
| if-02 | instruction_following | failed |  |  |  | 11 |  |
| if-03 | instruction_following | rendered | True | 0.783 | 19.4 | 1 | must_include, structure, cut_through_word, dialogue_continuity, framing |
| if-04 | instruction_following | rendered | True | 0.818 | 26.867 | 17 | structure, black_frames, cut_through_word, dialogue_continuity |
| if-05 | instruction_following | failed |  |  |  | 11 |  |
| pc-01 | pacing_scene_selection | rendered | True | 0.857 | 18.233 | 0 | adherence, structure, dialogue_continuity |
| pc-02 | pacing_scene_selection | rendered | True | 0.762 | 22.3 | 4 | structure, cut_through_word, dialogue_continuity, repeated_footage, shot_durations |
| pc-03 | pacing_scene_selection | rendered | True | 0.857 | 16.2 | 0 | structure, cut_through_word, dialogue_continuity |
| pc-04 | pacing_scene_selection | rendered | True | 0.864 | 19.867 | 2 | structure, dialogue_continuity, shot_durations |
| ps-01 | personalization | rendered | True | 0.818 | 24.433 | 0 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| ps-02 | personalization | rendered | True | 0.818 | 18.133 | 2 | preference_satisfaction, structure, dialogue_continuity, framing |
| ps-03 | personalization | rendered | True | 0.864 | 16.233 | 0 | structure, cut_through_word, dialogue_continuity |
| rs-01 | reference_style | rendered | True | 0.714 | 27.033 | 1 | structure, color_similarity, shot_length_similarity, cut_through_word, dialogue_continuity, framing |
| rs-02 | reference_style | rendered | True | 0.81 | 23.533 | 1 | structure, shot_length_similarity, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.667 | 21.067 | 2 | adherence, structure, shot_length_similarity, cut_through_word, dialogue_continuity, repeated_footage, framing |
| ac-04 | audio_captions | failed |  |  |  | 4 |  |
| if-06 | instruction_following | rendered | True | 0.957 | 18.9 | 0 | dialogue_continuity |
| pc-05 | pacing_scene_selection | rendered | True | 0.727 | 25.0 | 14 | adherence, structure, black_frames, cut_through_word, dead_air, dialogue_continuity |
| pc-06 | pacing_scene_selection | rendered | True | 0.857 | 12.567 | 1 | structure, dialogue_continuity, framing |
| ps-04 | personalization | rendered | True | 0.81 | 15.867 | 1 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| rs-04 | reference_style | rendered | True | 0.762 | 22.0 | 1 | adherence, structure, color_similarity, cut_through_word, dialogue_continuity |
