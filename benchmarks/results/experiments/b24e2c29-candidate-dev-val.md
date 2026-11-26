# Benchmark run b24e2c29-candidate-dev-val

- agent `editing-agent-0.3+97e3caa31076` · evaluator `eval-1.1` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-25T10:48:43+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 23 |
| completion_rate | 0.958 |
| technical_valid_rate | 0.958 |
| mean_pass_rate | 0.832 |
| mean_actions | 9.0 |
| repairs_per_task | 2.57 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 90% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 82% |
| instruction.must_exclude | 100% |
| instruction.must_include | 100% |
| instruction.preference_satisfaction | 25% |
| narrative.structure | 26% |
| style.caption_match | 100% |
| style.color_similarity | 75% |
| style.shot_length_similarity | 0% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 83% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 87% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 74% |
| temporal.dead_air | 96% |
| temporal.dialogue_continuity | 13% |
| temporal.repeated_footage | 87% |
| temporal.shot_durations | 52% |
| visual.framing | 78% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.909 | 24.4 | 2 | dialogue_continuity, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.909 | 17.067 | 1 | structure, dialogue_continuity |
| ac-03 | audio_captions | rendered | True | 0.682 | 23.867 | 3 | adherence, structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage, framing |
| if-01 | instruction_following | rendered | True | 0.913 | 23.6 | 0 | structure, shot_durations |
| if-02 | instruction_following | rendered | True | 0.913 | 16.467 | 3 | dialogue_continuity, shot_durations |
| if-03 | instruction_following | rendered | True | 0.913 | 21.9 | 1 | structure, dialogue_continuity |
| if-04 | instruction_following | rendered | True | 0.818 | 26.967 | 7 | structure, black_frames, cut_through_word, dialogue_continuity |
| if-05 | instruction_following | rendered | True | 0.87 | 26.9 | 0 | dialogue_continuity, shot_durations, framing |
| pc-01 | pacing_scene_selection | rendered | True | 0.857 | 18.5 | 0 | adherence, structure, dialogue_continuity |
| pc-02 | pacing_scene_selection | failed |  |  |  | 4 |  |
| pc-03 | pacing_scene_selection | rendered | True | 0.667 | 19.933 | 19 | accuracy, adherence, structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage |
| pc-04 | pacing_scene_selection | rendered | True | 0.864 | 19.267 | 0 | structure, dialogue_continuity, shot_durations |
| ps-01 | personalization | rendered | True | 0.864 | 23.6 | 0 | preference_satisfaction, structure, shot_durations |
| ps-02 | personalization | rendered | True | 0.909 | 18.133 | 0 | dialogue_continuity, shot_durations |
| ps-03 | personalization | rendered | True | 0.773 | 17.0 | 0 | preference_satisfaction, structure, cut_through_word, dialogue_continuity, framing |
| rs-01 | reference_style | rendered | True | 0.81 | 26.667 | 1 | structure, shot_length_similarity, frozen_frames, dialogue_continuity |
| rs-02 | reference_style | rendered | True | 0.857 | 23.167 | 2 | shot_length_similarity, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.714 | 19.767 | 1 | structure, shot_length_similarity, black_frames, cut_through_word, dead_air, dialogue_continuity |
| ac-04 | audio_captions | rendered | True | 0.864 | 20.433 | 2 | structure, dialogue_continuity, shot_durations |
| if-06 | instruction_following | rendered | True | 0.826 | 18.3 | 1 | accuracy, structure, dialogue_continuity, framing |
| pc-05 | pacing_scene_selection | rendered | True | 0.773 | 24.867 | 4 | adherence, structure, cut_through_word, dialogue_continuity, repeated_footage |
| pc-06 | pacing_scene_selection | rendered | True | 0.81 | 12.167 | 10 | structure, frozen_frames, dialogue_continuity, framing |
| ps-04 | personalization | rendered | True | 0.905 | 21.833 | 1 | preference_satisfaction, shot_durations |
| rs-04 | reference_style | rendered | True | 0.714 | 23.833 | 1 | structure, color_similarity, shot_length_similarity, frozen_frames, dialogue_continuity, shot_durations |
