# Benchmark run b24e2c29-candidate-confirm-dev-val

- agent `editing-agent-0.3+97e3caa31076` · evaluator `eval-1.1` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T08:22:40+00:00

| metric | value |
|---|---|
| tasks | 1 |
| completed | 1 |
| completion_rate | 1.0 |
| technical_valid_rate | 1.0 |
| mean_pass_rate | 0.905 |
| mean_actions | 17.0 |
| repairs_per_task | 7.0 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 100% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 100% |
| narrative.structure | 100% |
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
| pc-02 | pacing_scene_selection | rendered | True | 0.905 | 23.2 | 7 | dialogue_continuity, shot_durations |
