# Benchmark run 89615a10-candidate-dev-val

- agent `editing-agent-0.3+c95e6a96a4cf` · evaluator `eval-1.1` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-22T13:16:42+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 21 |
| completion_rate | 0.875 |
| technical_valid_rate | 0.875 |
| mean_pass_rate | 0.827 |
| mean_actions | 8.7 |
| repairs_per_task | 2.81 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 90% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 85% |
| instruction.must_exclude | 100% |
| instruction.must_include | 83% |
| instruction.preference_satisfaction | 57% |
| narrative.structure | 14% |
| style.caption_match | 0% |
| style.color_similarity | 75% |
| style.shot_length_similarity | 25% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 76% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 100% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 81% |
| temporal.dead_air | 100% |
| temporal.dialogue_continuity | 24% |
| temporal.repeated_footage | 100% |
| temporal.shot_durations | 43% |
| visual.framing | 67% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.826 | 23.6 | 0 | adherence, preference_satisfaction, structure, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.913 | 17.367 | 0 | dialogue_continuity, framing |
| ac-03 | audio_captions | rendered | True | 0.739 | 22.9 | 8 | accuracy, preference_satisfaction, structure, black_frames, cut_through_word, dialogue_continuity |
| if-02 | instruction_following | rendered | True | 0.958 | 17.533 | 1 | shot_durations |
| if-01 | instruction_following | rendered | True | 0.833 | 23.0 | 7 | structure, dialogue_continuity, shot_durations, framing |
| if-03 | instruction_following | rendered | True | 0.833 | 19.933 | 1 | must_include, structure, dialogue_continuity, framing |
| if-04 | instruction_following | rendered | True | 0.783 | 22.4 | 3 | adherence, structure, black_frames, cut_through_word, dialogue_continuity |
| if-05 | instruction_following | rendered | True | 0.792 | 29.5 | 7 | preference_satisfaction, structure, dialogue_continuity, shot_durations, framing |
| pc-01 | pacing_scene_selection | rendered | True | 0.909 | 18.5 | 0 | structure, dialogue_continuity |
| pc-02 | pacing_scene_selection | failed |  |  |  | 6 |  |
| pc-03 | pacing_scene_selection | rendered | True | 0.909 | 16.5 | 0 | black_frames, dialogue_continuity |
| pc-04 | pacing_scene_selection | rendered | True | 0.87 | 19.967 | 6 | structure, dialogue_continuity, shot_durations |
| ps-01 | personalization | rendered | True | 0.864 | 23.6 | 1 | preference_satisfaction, structure, shot_durations |
| ps-02 | personalization | rendered | True | 0.818 | 19.833 | 3 | preference_satisfaction, structure, dialogue_continuity, framing |
| rs-01 | reference_style | rendered | True | 0.8 | 25.267 | 2 | structure, caption_match, shot_length_similarity, dialogue_continuity, shot_durations |
| rs-02 | reference_style | rendered | True | 0.8 | 23.3 | 4 | structure, caption_match, shot_length_similarity, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.76 | 21.5 | 3 | structure, caption_match, shot_length_similarity, black_frames, cut_through_word, dialogue_continuity |
| ac-04 | audio_captions | rendered | True | 0.87 | 21.067 | 2 | structure, dialogue_continuity, shot_durations |
| if-06 | instruction_following | rendered | True | 0.792 | 22.333 | 6 | adherence, preference_satisfaction, structure, shot_durations, framing |
| pc-05 | pacing_scene_selection | failed |  |  |  | 5 |  |
| pc-06 | pacing_scene_selection | failed |  |  |  | 6 |  |
| ps-04 | personalization | rendered | True | 0.857 | 23.6 | 3 | preference_satisfaction, structure, shot_durations |
| rs-04 | reference_style | rendered | True | 0.72 | 22.0 | 2 | preference_satisfaction, structure, caption_match, color_similarity, dialogue_continuity, shot_durations, framing |
| ps-03 | personalization | rendered | True | 0.727 | 16.567 | 0 | accuracy, preference_satisfaction, structure, black_frames, cut_through_word, dialogue_continuity |
