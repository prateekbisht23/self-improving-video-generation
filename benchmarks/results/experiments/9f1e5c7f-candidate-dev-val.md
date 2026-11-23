# Benchmark run 9f1e5c7f-candidate-dev-val

- agent `editing-agent-0.3+a8f89929be9d` · evaluator `eval-1.1` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-23T12:48:48+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 24 |
| completion_rate | 1.0 |
| technical_valid_rate | 1.0 |
| mean_pass_rate | 0.808 |
| mean_actions | 8.9 |
| repairs_per_task | 2.42 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 95% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 75% |
| instruction.must_exclude | 100% |
| instruction.must_include | 100% |
| instruction.preference_satisfaction | 25% |
| narrative.structure | 13% |
| style.caption_match | 100% |
| style.color_similarity | 50% |
| style.shot_length_similarity | 0% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 79% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 92% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 62% |
| temporal.dead_air | 100% |
| temporal.dialogue_continuity | 8% |
| temporal.repeated_footage | 75% |
| temporal.shot_durations | 62% |
| visual.framing | 54% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.864 | 23.267 | 0 | adherence, structure, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.864 | 17.067 | 0 | structure, dialogue_continuity, framing |
| ac-03 | audio_captions | rendered | True | 0.727 | 23.067 | 14 | structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage, framing |
| if-01 | instruction_following | rendered | True | 0.826 | 22.7 | 1 | structure, dialogue_continuity, shot_durations, framing |
| if-02 | instruction_following | rendered | True | 0.957 | 17.233 | 2 | shot_durations |
| if-03 | instruction_following | rendered | True | 0.913 | 21.567 | 1 | dialogue_continuity, framing |
| if-04 | instruction_following | rendered | True | 0.682 | 22.9 | 1 | adherence, structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage, framing |
| if-05 | instruction_following | rendered | True | 0.783 | 30.0 | 13 | adherence, structure, cut_through_word, dialogue_continuity, repeated_footage |
| pc-01 | pacing_scene_selection | rendered | True | 0.857 | 18.233 | 0 | adherence, structure, dialogue_continuity |
| pc-02 | pacing_scene_selection | rendered | True | 0.81 | 22.8 | 2 | structure, cut_through_word, dialogue_continuity, framing |
| pc-03 | pacing_scene_selection | rendered | True | 0.619 | 15.7 | 8 | accuracy, adherence, structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage, framing |
| pc-04 | pacing_scene_selection | rendered | True | 0.818 | 17.6 | 3 | structure, dialogue_continuity, repeated_footage, shot_durations |
| ps-01 | personalization | rendered | True | 0.818 | 16.667 | 0 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| ps-02 | personalization | rendered | True | 0.818 | 19.8 | 2 | preference_satisfaction, structure, dialogue_continuity, framing |
| ps-03 | personalization | rendered | True | 0.773 | 20.967 | 0 | structure, black_frames, cut_through_word, dialogue_continuity, framing |
| rs-01 | reference_style | rendered | True | 0.714 | 23.567 | 1 | structure, color_similarity, shot_length_similarity, frozen_frames, dialogue_continuity, shot_durations |
| rs-02 | reference_style | rendered | True | 0.762 | 24.033 | 1 | structure, shot_length_similarity, cut_through_word, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.8 | 20.2 | 2 | shot_length_similarity, black_frames, cut_through_word, dialogue_continuity |
| ac-04 | audio_captions | rendered | True | 0.864 | 18.3 | 3 | structure, dialogue_continuity, shot_durations |
| if-06 | instruction_following | rendered | True | 0.957 | 18.9 | 0 | dialogue_continuity |
| pc-05 | pacing_scene_selection | rendered | True | 0.864 | 21.2 | 0 | structure, cut_through_word, dialogue_continuity |
| pc-06 | pacing_scene_selection | rendered | True | 0.81 | 14.1 | 4 | structure, dialogue_continuity, repeated_footage, framing |
| ps-04 | personalization | rendered | True | 0.818 | 20.967 | 0 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| rs-04 | reference_style | rendered | True | 0.667 | 23.3 | 0 | adherence, structure, color_similarity, shot_length_similarity, frozen_frames, dialogue_continuity, framing |
