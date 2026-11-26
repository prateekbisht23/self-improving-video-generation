# Benchmark run 9fe70e55-candidate-dev-val

- agent `editing-agent-0.3+a8f89929be9d` · evaluator `eval-1.2` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T10:27:52+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 23 |
| completion_rate | 0.958 |
| technical_valid_rate | 0.917 |
| mean_pass_rate | 0.82 |
| mean_actions | 9.0 |
| repairs_per_task | 2.48 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 90% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 68% |
| instruction.must_exclude | 100% |
| instruction.must_include | 86% |
| instruction.preference_satisfaction | 33% |
| narrative.structure | 22% |
| style.caption_match | 100% |
| style.color_similarity | 75% |
| style.shot_length_similarity | 0% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 87% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 96% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 52% |
| temporal.dead_air | 100% |
| temporal.dialogue_continuity | 17% |
| temporal.repeated_footage | 87% |
| temporal.shot_durations | 56% |
| visual.framing | 65% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.864 | 23.0 | 0 | structure, dialogue_continuity, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.909 | 16.733 | 0 | structure, dialogue_continuity |
| ac-03 | audio_captions | rendered | True | 0.818 | 23.067 | 2 | structure, cut_through_word, dialogue_continuity, framing |
| if-01 | instruction_following | rendered | True | 0.913 | 21.233 | 1 | cut_through_word, shot_durations |
| if-02 | instruction_following | rendered | True | 0.957 | 17.2 | 1 | shot_durations |
| if-03 | instruction_following | rendered | True | 0.957 | 19.433 | 1 | framing |
| if-04 | instruction_following | rendered | True | 0.727 | 24.667 | 3 | adherence, structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage |
| if-05 | instruction_following | rendered | True | 0.783 | 27.0 | 8 | adherence, structure, cut_through_word, dialogue_continuity, repeated_footage |
| pc-01 | pacing_scene_selection | rendered | True | 0.857 | 18.233 | 0 | adherence, structure, dialogue_continuity |
| pc-02 | pacing_scene_selection | rendered | True | 0.857 | 20.833 | 0 | dialogue_continuity, shot_durations, framing |
| pc-03 | pacing_scene_selection | rendered | True | 0.857 | 18.133 | 4 | structure, cut_through_word, dialogue_continuity |
| pc-04 | pacing_scene_selection | rendered | True | 0.818 | 20.0 | 4 | adherence, structure, dialogue_continuity, shot_durations |
| ps-01 | personalization | rendered | True | 0.818 | 23.0 | 1 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| ps-02 | personalization | failed |  |  |  | 13 |  |
| ps-03 | personalization | rendered | True | 0.773 | 19.367 | 1 | accuracy, structure, cut_through_word, dialogue_continuity, framing |
| rs-01 | reference_style | rendered | False | 0.714 | 28.033 | 0 | structure, shot_length_similarity, black_frames, frozen_frames, dialogue_continuity, shot_durations |
| rs-02 | reference_style | rendered | True | 0.762 | 21.5 | 4 | structure, shot_length_similarity, cut_through_word, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.667 | 22.3 | 0 | adherence, structure, shot_length_similarity, black_frames, cut_through_word, dialogue_continuity, framing |
| ac-04 | audio_captions | rendered | True | 0.864 | 20.667 | 2 | structure, cut_through_word, shot_durations |
| if-06 | instruction_following | rendered | True | 0.652 | 24.0 | 24 | accuracy, adherence, must_include, structure, cut_through_word, dialogue_continuity, repeated_footage, framing |
| pc-05 | pacing_scene_selection | rendered | True | 0.864 | 22.533 | 0 | structure, cut_through_word, dialogue_continuity |
| pc-06 | pacing_scene_selection | rendered | True | 0.905 | 14.433 | 1 | dialogue_continuity, framing |
| ps-04 | personalization | rendered | True | 0.81 | 19.4 | 0 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| rs-04 | reference_style | rendered | True | 0.714 | 23.3 | 0 | adherence, structure, color_similarity, shot_length_similarity, dialogue_continuity, framing |
