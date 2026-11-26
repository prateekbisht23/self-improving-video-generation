# Benchmark run b24e2c29-baseline-dev-val

- agent `editing-agent-0.2+d43dbd596cae` · evaluator `eval-1.1` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-25T10:47:27+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 22 |
| completion_rate | 0.917 |
| technical_valid_rate | 0.917 |
| mean_pass_rate | 0.812 |
| mean_actions | 8.9 |
| repairs_per_task | 2.14 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 77% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 68% |
| instruction.must_exclude | 100% |
| instruction.must_include | 100% |
| instruction.preference_satisfaction | 25% |
| narrative.structure | 23% |
| style.caption_match | 0% |
| style.color_similarity | 50% |
| style.shot_length_similarity | 0% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 91% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 100% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 41% |
| temporal.dead_air | 96% |
| temporal.dialogue_continuity | 14% |
| temporal.repeated_footage | 91% |
| temporal.shot_durations | 59% |
| visual.framing | 77% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.773 | 23.233 | 4 | adherence, structure, cut_through_word, dialogue_continuity, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.864 | 18.567 | 1 | accuracy, dialogue_continuity, framing |
| ac-03 | audio_captions | failed |  |  |  | 7 |  |
| if-01 | instruction_following | rendered | True | 0.826 | 23.233 | 1 | structure, cut_through_word, dialogue_continuity, shot_durations |
| if-02 | instruction_following | rendered | True | 0.957 | 17.2 | 1 | shot_durations |
| if-03 | instruction_following | rendered | True | 0.87 | 21.5 | 1 | structure, cut_through_word, dialogue_continuity |
| if-04 | instruction_following | rendered | True | 0.727 | 20.0 | 2 | adherence, structure, black_frames, cut_through_word, dialogue_continuity, framing |
| if-05 | instruction_following | rendered | True | 0.913 | 29.867 | 0 | dialogue_continuity, shot_durations |
| pc-01 | pacing_scene_selection | rendered | True | 0.857 | 19.033 | 1 | adherence, structure, dialogue_continuity |
| pc-02 | pacing_scene_selection | rendered | True | 0.857 | 20.767 | 0 | cut_through_word, dialogue_continuity, shot_durations |
| pc-03 | pacing_scene_selection | rendered | True | 0.667 | 20.0 | 19 | accuracy, adherence, structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage |
| pc-04 | pacing_scene_selection | rendered | True | 0.864 | 18.233 | 0 | adherence, structure, dialogue_continuity |
| ps-01 | personalization | rendered | True | 0.864 | 23.267 | 0 | preference_satisfaction, structure, shot_durations |
| ps-02 | personalization | rendered | True | 0.818 | 16.4 | 3 | preference_satisfaction, structure, dialogue_continuity, framing |
| ps-03 | personalization | rendered | True | 0.864 | 20.067 | 0 | structure, cut_through_word, dialogue_continuity |
| rs-01 | reference_style | rendered | True | 0.667 | 20.333 | 5 | accuracy, structure, caption_match, color_similarity, shot_length_similarity, cut_through_word, dialogue_continuity, framing |
| rs-02 | reference_style | rendered | True | 0.75 | 22.533 | 1 | structure, caption_match, shot_length_similarity, cut_through_word, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.792 | 19.833 | 1 | structure, caption_match, shot_length_similarity, cut_through_word, dialogue_continuity |
| ac-04 | audio_captions | failed |  |  |  | 4 |  |
| if-06 | instruction_following | rendered | True | 0.783 | 24.0 | 6 | accuracy, structure, cut_through_word, dialogue_continuity, repeated_footage |
| pc-05 | pacing_scene_selection | rendered | True | 0.636 | 21.467 | 0 | accuracy, adherence, structure, cut_through_word, dead_air, dialogue_continuity, shot_durations, framing |
| pc-06 | pacing_scene_selection | rendered | True | 0.905 | 14.7 | 0 | structure, dialogue_continuity |
| ps-04 | personalization | rendered | True | 0.909 | 21.7 | 1 | preference_satisfaction, shot_durations |
| rs-04 | reference_style | rendered | True | 0.708 | 23.1 | 0 | adherence, structure, caption_match, color_similarity, shot_length_similarity, cut_through_word, dialogue_continuity |
