# Benchmark run 9f1e5c7f-baseline-dev-val

- agent `editing-agent-0.2+d43dbd596cae` · evaluator `eval-1.1` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-23T12:32:18+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 23 |
| completion_rate | 0.958 |
| technical_valid_rate | 0.958 |
| mean_pass_rate | 0.818 |
| mean_actions | 8.7 |
| repairs_per_task | 1.91 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 91% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 78% |
| instruction.must_exclude | 100% |
| instruction.must_include | 100% |
| instruction.preference_satisfaction | 25% |
| narrative.structure | 17% |
| style.caption_match | 0% |
| style.color_similarity | 25% |
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
| temporal.cut_through_word | 52% |
| temporal.dead_air | 100% |
| temporal.dialogue_continuity | 13% |
| temporal.repeated_footage | 100% |
| temporal.shot_durations | 48% |
| visual.framing | 61% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.864 | 24.833 | 1 | structure, dialogue_continuity, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.955 | 19.467 | 0 | framing |
| ac-03 | audio_captions | rendered | True | 0.727 | 20.533 | 2 | accuracy, structure, black_frames, cut_through_word, dialogue_continuity, framing |
| if-01 | instruction_following | rendered | True | 0.826 | 23.633 | 5 | structure, cut_through_word, dialogue_continuity, shot_durations |
| if-02 | instruction_following | rendered | True | 0.87 | 15.733 | 2 | structure, dialogue_continuity, shot_durations |
| if-03 | instruction_following | rendered | True | 1.0 | 19.433 | 1 |  |
| if-04 | instruction_following | rendered | True | 0.818 | 20.433 | 4 | structure, black_frames, cut_through_word, dialogue_continuity |
| if-05 | instruction_following | rendered | True | 0.87 | 29.633 | 1 | dialogue_continuity, shot_durations, framing |
| pc-01 | pacing_scene_selection | rendered | True | 0.762 | 15.367 | 3 | adherence, structure, cut_through_word, dialogue_continuity, shot_durations |
| pc-02 | pacing_scene_selection | rendered | True | 0.81 | 21.3 | 0 | structure, dialogue_continuity, shot_durations, framing |
| pc-03 | pacing_scene_selection | rendered | True | 0.762 | 17.1 | 5 | accuracy, adherence, cut_through_word, dialogue_continuity, framing |
| pc-04 | pacing_scene_selection | rendered | True | 0.864 | 17.733 | 1 | adherence, structure, shot_durations |
| ps-01 | personalization | rendered | True | 0.773 | 24.733 | 2 | preference_satisfaction, structure, cut_through_word, dialogue_continuity, shot_durations |
| ps-02 | personalization | rendered | True | 0.818 | 19.867 | 10 | preference_satisfaction, structure, cut_through_word, dialogue_continuity |
| ps-03 | personalization | rendered | True | 0.864 | 17.267 | 0 | structure, cut_through_word, dialogue_continuity |
| rs-01 | reference_style | rendered | True | 0.792 | 23.4 | 0 | structure, caption_match, color_similarity, shot_length_similarity, dialogue_continuity |
| rs-02 | reference_style | rendered | True | 0.75 | 24.2 | 2 | structure, caption_match, shot_length_similarity, cut_through_word, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.667 | 22.567 | 3 | adherence, structure, caption_match, color_similarity, shot_length_similarity, cut_through_word, dialogue_continuity, framing |
| ac-04 | audio_captions | rendered | True | 0.818 | 19.667 | 2 | structure, cut_through_word, dialogue_continuity, shot_durations |
| if-06 | instruction_following | rendered | True | 0.87 | 18.133 | 0 | structure, dialogue_continuity, framing |
| pc-05 | pacing_scene_selection | failed |  |  |  | 4 |  |
| pc-06 | pacing_scene_selection | rendered | True | 0.857 | 12.033 | 0 | structure, dialogue_continuity, framing |
| ps-04 | personalization | rendered | True | 0.818 | 22.133 | 0 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| rs-04 | reference_style | rendered | True | 0.667 | 22.0 | 0 | adherence, structure, caption_match, color_similarity, shot_length_similarity, dialogue_continuity, shot_durations, framing |
