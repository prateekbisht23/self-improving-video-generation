# Benchmark run 9fe70e55-candidate-confirm-dev-val

- agent `editing-agent-0.3+a8f89929be9d` · evaluator `eval-1.2` · dataset `bench-v1-840ca30bb4` · splits ['development', 'validation']
- planner `google_genai:gemini-3.5-flash-lite` · judge `google_genai:gemini-3.5-flash-lite` · started 2026-11-26T12:35:23+00:00

| metric | value |
|---|---|
| tasks | 1 |
| completed | 1 |
| completion_rate | 1.0 |
| technical_valid_rate | 1.0 |
| mean_pass_rate | 0.818 |
| mean_actions | 9.0 |
| repairs_per_task | 2.0 |

## Check pass rates

| check | pass rate |
|---|---|
| captions.accuracy | 0% |
| captions.speech_coverage | 100% |
| captions.sync | 100% |
| instruction.adherence | 100% |
| instruction.preference_satisfaction | 0% |
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
| temporal.shot_durations | 100% |
| visual.framing | 100% |

## Tasks

| task | category | status | gate | pass rate | duration | repairs | failed |
|---|---|---|---|---|---|---|---|
| ps-02 | personalization | rendered | True | 0.818 | 16.233 | 2 | accuracy, preference_satisfaction, structure, dialogue_continuity |
