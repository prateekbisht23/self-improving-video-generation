# Benchmark run 03fbf7cf-candidate-dev-val

- agent `editing-agent-0.3+97e3caa31076` · evaluator `eval-1.1` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-24T18:09:35+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 22 |
| completion_rate | 0.917 |
| technical_valid_rate | 0.917 |
| mean_pass_rate | 0.819 |
| mean_actions | 7.3 |
| repairs_per_task | 1.0 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 94% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 73% |
| instruction.must_exclude | 100% |
| instruction.must_include | 100% |
| instruction.preference_satisfaction | 50% |
| narrative.structure | 14% |
| style.caption_match | 100% |
| style.color_similarity | 50% |
| style.shot_length_similarity | 0% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 77% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 91% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 77% |
| temporal.dead_air | 96% |
| temporal.dialogue_continuity | 9% |
| temporal.repeated_footage | 100% |
| temporal.shot_durations | 46% |
| visual.framing | 64% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.909 | 23.6 | 0 | structure, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.864 | 17.367 | 0 | structure, dialogue_continuity, framing |
| ac-03 | audio_captions | rendered | True | 0.727 | 23.5 | 2 | adherence, structure, black_frames, cut_through_word, dialogue_continuity, framing |
| if-01 | instruction_following | rendered | True | 0.87 | 22.7 | 3 | structure, dialogue_continuity, shot_durations |
| if-02 | instruction_following | rendered | True | 0.913 | 17.333 | 2 | structure, shot_durations |
| if-04 | instruction_following | rendered | True | 0.818 | 25.0 | 3 | structure, black_frames, cut_through_word, dialogue_continuity |
| if-05 | instruction_following | rendered | True | 0.826 | 25.033 | 1 | structure, dialogue_continuity, shot_durations, framing |
| pc-01 | pacing_scene_selection | rendered | True | 0.81 | 17.3 | 3 | adherence, structure, dialogue_continuity, shot_durations |
| pc-03 | pacing_scene_selection | failed |  |  |  | 6 |  |
| pc-04 | pacing_scene_selection | rendered | True | 0.818 | 18.5 | 0 | adherence, structure, dialogue_continuity, shot_durations |
| ps-01 | personalization | rendered | True | 0.818 | 20.933 | 1 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| ps-02 | personalization | rendered | True | 0.909 | 17.8 | 0 | dialogue_continuity, framing |
| ps-03 | personalization | rendered | True | 0.818 | 17.333 | 0 | structure, black_frames, cut_through_word, dialogue_continuity |
| rs-01 | reference_style | rendered | True | 0.81 | 26.167 | 1 | shot_length_similarity, frozen_frames, dialogue_continuity, framing |
| rs-02 | reference_style | rendered | True | 0.81 | 23.867 | 1 | structure, shot_length_similarity, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.619 | 20.833 | 2 | adherence, structure, color_similarity, shot_length_similarity, black_frames, cut_through_word, dialogue_continuity, framing |
| if-03 | instruction_following | rendered | True | 0.87 | 21.9 | 1 | structure, dialogue_continuity, framing |
| pc-02 | pacing_scene_selection | failed |  |  |  | 5 |  |
| ac-04 | audio_captions | rendered | True | 0.864 | 18.433 | 1 | structure, dialogue_continuity, shot_durations |
| if-06 | instruction_following | rendered | True | 0.913 | 19.2 | 0 | dialogue_continuity, shot_durations |
| pc-05 | pacing_scene_selection | rendered | True | 0.636 | 22.833 | 1 | adherence, structure, black_frames, cut_through_word, dead_air, dialogue_continuity, shot_durations, framing |
| pc-06 | pacing_scene_selection | rendered | True | 0.857 | 14.9 | 0 | accuracy, structure, dialogue_continuity |
| ps-04 | personalization | rendered | True | 0.818 | 17.0 | 0 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| rs-04 | reference_style | rendered | True | 0.714 | 19.967 | 0 | adherence, structure, color_similarity, shot_length_similarity, frozen_frames, dialogue_continuity |
