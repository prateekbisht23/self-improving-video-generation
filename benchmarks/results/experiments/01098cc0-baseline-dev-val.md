# Benchmark run 01098cc0-baseline-dev-val

- agent `editing-agent-0.2+d43dbd596cae` · evaluator `eval-1.3` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T13:17:29+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 23 |
| completion_rate | 0.958 |
| technical_valid_rate | 0.958 |
| mean_pass_rate | 0.824 |
| mean_actions | 8.0 |
| repairs_per_task | 1.39 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 100% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 74% |
| instruction.must_exclude | 100% |
| instruction.must_include | 100% |
| instruction.preference_satisfaction | 50% |
| narrative.structure | 9% |
| style.caption_match | 0% |
| style.color_similarity | 50% |
| style.shot_length_similarity | 0% |
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
| temporal.cut_through_word | 44% |
| temporal.dead_air | 96% |
| temporal.dialogue_continuity | 17% |
| temporal.repeated_footage | 96% |
| temporal.shot_durations | 52% |
| visual.framing | 83% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.909 | 23.267 | 0 | structure, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.909 | 17.067 | 0 | structure, dialogue_continuity |
| ac-03 | audio_captions | rendered | True | 0.864 | 23.467 | 4 | structure, cut_through_word, dialogue_continuity |
| if-01 | instruction_following | rendered | True | 0.826 | 23.2 | 2 | structure, cut_through_word, dialogue_continuity, shot_durations |
| if-02 | instruction_following | rendered | True | 0.913 | 16.2 | 2 | dialogue_continuity, shot_durations |
| if-03 | instruction_following | rendered | True | 0.826 | 20.133 | 3 | structure, cut_through_word, dialogue_continuity, framing |
| if-04 | instruction_following | rendered | True | 0.727 | 20.9 | 2 | adherence, structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage |
| if-05 | instruction_following | rendered | True | 0.826 | 29.4 | 1 | structure, cut_through_word, dialogue_continuity, shot_durations |
| pc-01 | pacing_scene_selection | rendered | True | 0.762 | 15.867 | 2 | adherence, structure, cut_through_word, dialogue_continuity, shot_durations |
| pc-02 | pacing_scene_selection | rendered | True | 0.857 | 21.8 | 1 | structure, cut_through_word, shot_durations |
| pc-03 | pacing_scene_selection | rendered | True | 0.762 | 19.633 | 1 | adherence, structure, cut_through_word, dialogue_continuity, framing |
| pc-04 | pacing_scene_selection | rendered | True | 0.864 | 15.967 | 1 | adherence, structure, dialogue_continuity |
| ps-01 | personalization | rendered | True | 0.864 | 23.267 | 0 | preference_satisfaction, structure, shot_durations |
| ps-02 | personalization | rendered | True | 0.818 | 19.367 | 3 | preference_satisfaction, structure, cut_through_word, dialogue_continuity |
| ps-03 | personalization | rendered | True | 0.818 | 15.833 | 0 | structure, black_frames, cut_through_word, dialogue_continuity |
| rs-01 | reference_style | rendered | True | 0.792 | 22.967 | 0 | structure, caption_match, color_similarity, shot_length_similarity, dialogue_continuity |
| rs-02 | reference_style | rendered | True | 0.792 | 25.0 | 2 | structure, caption_match, shot_length_similarity, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.75 | 20.033 | 2 | structure, caption_match, shot_length_similarity, black_frames, cut_through_word, dialogue_continuity |
| ac-04 | audio_captions | failed |  |  |  | 4 |  |
| if-06 | instruction_following | rendered | True | 0.957 | 23.567 | 1 | dialogue_continuity |
| pc-05 | pacing_scene_selection | rendered | True | 0.682 | 21.967 | 0 | adherence, structure, cut_through_word, dead_air, dialogue_continuity, shot_durations, framing |
| pc-06 | pacing_scene_selection | rendered | True | 0.857 | 13.9 | 2 | structure, cut_through_word, framing |
| ps-04 | personalization | rendered | True | 0.864 | 21.7 | 3 | structure, dialogue_continuity, shot_durations |
| rs-04 | reference_style | rendered | True | 0.708 | 22.167 | 0 | adherence, structure, caption_match, color_similarity, shot_length_similarity, dialogue_continuity, shot_durations |
