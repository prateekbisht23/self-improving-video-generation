# Benchmark run 9fe70e55-baseline-dev-val

- agent `editing-agent-0.2+d43dbd596cae` · evaluator `eval-1.2` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T10:27:25+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 23 |
| completion_rate | 0.958 |
| technical_valid_rate | 0.958 |
| mean_pass_rate | 0.824 |
| mean_actions | 8.0 |
| repairs_per_task | 1.57 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 96% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 91% |
| instruction.must_exclude | 100% |
| instruction.must_include | 100% |
| instruction.preference_satisfaction | 25% |
| narrative.structure | 13% |
| style.caption_match | 0% |
| style.color_similarity | 75% |
| style.shot_length_similarity | 25% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 87% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 100% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 52% |
| temporal.dead_air | 91% |
| temporal.dialogue_continuity | 22% |
| temporal.repeated_footage | 91% |
| temporal.shot_durations | 56% |
| visual.framing | 52% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.909 | 23.267 | 0 | structure, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.864 | 17.067 | 0 | structure, dialogue_continuity, framing |
| ac-03 | audio_captions | rendered | True | 0.682 | 22.833 | 2 | accuracy, structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage, framing |
| if-01 | instruction_following | rendered | True | 0.913 | 24.067 | 0 | dialogue_continuity, shot_durations |
| if-02 | instruction_following | rendered | True | 0.87 | 19.367 | 1 | structure, cut_through_word, shot_durations |
| if-03 | instruction_following | rendered | True | 0.87 | 15.933 | 4 | structure, cut_through_word, framing |
| if-04 | instruction_following | rendered | True | 0.773 | 22.233 | 4 | structure, black_frames, cut_through_word, dialogue_continuity, shot_durations |
| if-05 | instruction_following | rendered | True | 0.913 | 28.967 | 0 | dialogue_continuity, framing |
| pc-01 | pacing_scene_selection | rendered | True | 0.857 | 18.233 | 0 | adherence, structure, dialogue_continuity |
| pc-02 | pacing_scene_selection | rendered | True | 0.81 | 21.267 | 7 | structure, cut_through_word, dead_air, dialogue_continuity |
| pc-03 | pacing_scene_selection | failed |  |  |  | 6 |  |
| pc-04 | pacing_scene_selection | rendered | True | 0.864 | 19.867 | 3 | structure, dialogue_continuity, shot_durations |
| ps-01 | personalization | rendered | True | 0.909 | 21.7 | 1 | preference_satisfaction, shot_durations |
| ps-02 | personalization | rendered | True | 0.773 | 20.0 | 6 | preference_satisfaction, structure, cut_through_word, dialogue_continuity, framing |
| ps-03 | personalization | rendered | True | 0.773 | 19.5 | 1 | structure, black_frames, cut_through_word, dialogue_continuity, framing |
| rs-01 | reference_style | rendered | True | 0.792 | 25.4 | 0 | structure, caption_match, shot_length_similarity, dialogue_continuity, framing |
| rs-02 | reference_style | rendered | True | 0.75 | 24.267 | 2 | structure, caption_match, shot_length_similarity, cut_through_word, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.708 | 23.867 | 0 | structure, caption_match, cut_through_word, dead_air, dialogue_continuity, shot_durations, framing |
| ac-04 | audio_captions | rendered | True | 0.864 | 18.1 | 1 | structure, cut_through_word, shot_durations |
| if-06 | instruction_following | rendered | True | 0.913 | 19.1 | 1 | structure, dialogue_continuity |
| pc-05 | pacing_scene_selection | rendered | True | 0.773 | 24.067 | 1 | adherence, structure, cut_through_word, dialogue_continuity, framing |
| pc-06 | pacing_scene_selection | rendered | True | 0.81 | 12.467 | 1 | structure, dialogue_continuity, repeated_footage, framing |
| ps-04 | personalization | rendered | True | 0.818 | 15.867 | 1 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| rs-04 | reference_style | rendered | True | 0.75 | 24.367 | 0 | structure, caption_match, color_similarity, shot_length_similarity, dialogue_continuity, framing |
