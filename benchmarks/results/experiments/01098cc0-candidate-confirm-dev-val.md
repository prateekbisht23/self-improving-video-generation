# Benchmark run 01098cc0-candidate-confirm-dev-val

- agent `editing-agent-0.3+20c1ce52b422` · evaluator `eval-1.3` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T13:55:27+00:00

| metric | value |
|---|---|
| tasks | 2 |
| completed | 2 |
| completion_rate | 1.0 |
| technical_valid_rate | 1.0 |
| mean_pass_rate | 0.87 |
| mean_actions | 7.0 |
| repairs_per_task | 0.5 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 100% |
| captions.present | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 100% |
| instruction.must_exclude | 100% |
| instruction.must_include | 100% |
| narrative.structure | 0% |
| technical.aspect_ratio | 100% |
| technical.audio_present | 100% |
| technical.av_stream_alignment | 100% |
| technical.black_frames | 100% |
| technical.duration_in_range | 100% |
| technical.file_valid | 100% |
| technical.frozen_frames | 100% |
| technical.loudness | 100% |
| technical.missing_media | 100% |
| technical.resolution | 100% |
| temporal.cut_through_word | 100% |
| temporal.dead_air | 100% |
| temporal.dialogue_continuity | 0% |
| temporal.repeated_footage | 100% |
| temporal.shot_durations | 0% |
| visual.framing | 100% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| if-02 | instruction_following | rendered | True | 0.87 | 19.9 | 1 | structure, dialogue_continuity, shot_durations |
| if-05 | instruction_following | rendered | True | 0.87 | 25.7 | 0 | structure, dialogue_continuity, shot_durations |
