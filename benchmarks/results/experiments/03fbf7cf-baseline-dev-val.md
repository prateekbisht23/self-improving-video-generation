# Benchmark run 03fbf7cf-baseline-dev-val

- agent `editing-agent-0.2+d43dbd596cae` · evaluator `eval-1.1` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-24T18:08:41+00:00

| metric | value |
|---|---|
| tasks | 24 |
| completed | 22 |
| completion_rate | 0.917 |
| technical_valid_rate | 0.917 |
| mean_pass_rate | 0.831 |
| mean_actions | 8.0 |
| repairs_per_task | 1.59 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 100% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 77% |
| instruction.must_include | 100% |
| instruction.preference_satisfaction | 25% |
| narrative.structure | 23% |
| style.caption_match | 0% |
| style.color_similarity | 100% |
| style.shot_length_similarity | 0% |
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
| temporal.cut_through_word | 55% |
| temporal.dead_air | 96% |
| temporal.dialogue_continuity | 4% |
| temporal.repeated_footage | 91% |
| temporal.shot_durations | 68% |
| visual.framing | 64% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ac-01 | audio_captions | rendered | True | 0.864 | 23.267 | 1 | structure, dialogue_continuity, shot_durations |
| ac-02 | audio_captions | rendered | True | 0.909 | 17.067 | 0 | structure, dialogue_continuity |
| ac-03 | audio_captions | rendered | True | 0.682 | 23.3 | 5 | adherence, structure, black_frames, cut_through_word, dialogue_continuity, repeated_footage, framing |
| if-01 | instruction_following | rendered | True | 0.87 | 24.0 | 2 | dialogue_continuity, shot_durations, framing |
| if-03 | instruction_following | rendered | True | 0.957 | 21.567 | 1 | dialogue_continuity |
| pc-01 | pacing_scene_selection | rendered | True | 0.857 | 18.233 | 0 | adherence, structure, dialogue_continuity |
| pc-02 | pacing_scene_selection | rendered | True | 0.762 | 21.767 | 2 | structure, cut_through_word, dialogue_continuity, repeated_footage, framing |
| pc-03 | pacing_scene_selection | rendered | True | 0.905 | 18.4 | 8 | cut_through_word, dialogue_continuity |
| pc-04 | pacing_scene_selection | rendered | True | 0.864 | 17.033 | 0 | adherence, structure, dialogue_continuity |
| ps-01 | personalization | rendered | True | 0.818 | 16.667 | 0 | preference_satisfaction, structure, dialogue_continuity, shot_durations |
| ps-02 | personalization | rendered | True | 0.864 | 18.167 | 1 | preference_satisfaction, structure, dialogue_continuity |
| ps-03 | personalization | rendered | True | 0.818 | 17.0 | 0 | structure, cut_through_word, dialogue_continuity, framing |
| rs-01 | reference_style | rendered | True | 0.75 | 27.367 | 1 | structure, caption_match, shot_length_similarity, cut_through_word, dialogue_continuity, framing |
| rs-02 | reference_style | rendered | True | 0.75 | 24.7 | 1 | structure, caption_match, shot_length_similarity, cut_through_word, dialogue_continuity, shot_durations |
| rs-03 | reference_style | rendered | True | 0.75 | 20.467 | 6 | structure, caption_match, shot_length_similarity, black_frames, cut_through_word, dialogue_continuity |
| if-02 | instruction_following | failed |  |  |  | 4 |  |
| if-04 | instruction_following | rendered | True | 0.727 | 24.233 | 3 | adherence, structure, black_frames, cut_through_word, dialogue_continuity, shot_durations |
| if-05 | instruction_following | rendered | True | 0.913 | 25.533 | 1 | dialogue_continuity, framing |
| ac-04 | audio_captions | rendered | True | 0.818 | 18.7 | 1 | structure, cut_through_word, dialogue_continuity, shot_durations |
| if-06 | instruction_following | rendered | True | 0.913 | 21.233 | 0 | structure, dialogue_continuity |
| pc-05 | pacing_scene_selection | rendered | True | 0.727 | 23.667 | 1 | adherence, structure, cut_through_word, dead_air, dialogue_continuity, framing |
| pc-06 | pacing_scene_selection | rendered | True | 0.905 | 12.3 | 1 | dialogue_continuity, framing |
| ps-04 | personalization | rendered | True | 0.864 | 23.267 | 0 | preference_satisfaction, structure, shot_durations |
| rs-04 |  | error |  |  |  |  |  |
