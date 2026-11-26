# Benchmark run 25bed9cd-candidate-confirm-extra-dev-val

- agent `editing-agent-0.3+a8f89929be9d` · evaluator `eval-1.3` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T12:49:31+00:00

| metric | value |
|---|---|
| tasks | 1 |
| completed | 1 |
| completion_rate | 1.0 |
| technical_valid_rate | 1.0 |
| mean_pass_rate | 0.762 |
| mean_actions | 13.0 |
| repairs_per_task | 2.0 |

## Check pass rates

| check | pass rate |
|---|---|
| instruction.adherence | 100% |
| narrative.structure | 0% |
| style.caption_match | 100% |
| style.color_similarity | 0% |
| style.shot_length_similarity | 0% |
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
| rs-01 | reference_style | rendered | True | 0.762 | 27.533 | 2 | structure, color_similarity, shot_length_similarity, dialogue_continuity, shot_durations |
