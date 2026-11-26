# 13 — Independent evaluation: deterministic checks, signals, and LLM judges

Code: `evaluation/` (features, evaluators, graph), `services/worker/evaluation.py`.

## Independence is a design rule, not a hope
- The evaluator measures the **rendered file**: ffprobe, `blackdetect`, `freezedetect`, `silencedetect`, `ebur128`, cut detection, and a **fresh Whisper transcription of the output audio**.
- It never sees the agent's plan or reasoning. Structural facts from the timeline (which clips, captions and source ranges) are allowed, because they describe *what was made*, not *why*.
- `test_evaluation_never_imports_the_agent` parses every file in `evaluation/` and fails if one imports `agent` or `services`.
- It runs as a separate RQ job after rendering, with its own LangGraph graph, prompts, model role (`judge`) and version (`eval-1.0`).

## Three kinds of check, in order of trust
| kind | examples | trust |
|---|---|---|
| deterministic | duration, resolution/aspect, audio present, stream alignment, black/frozen frames, loudness, repeated footage, cut through a word, mid-sentence cuts | high: same input, same answer |
| signal | caption WER vs output transcription, caption sync offset, speech coverage, style similarity | medium: measured, but the reference is itself an estimate |
| model | instruction adherence, narrative (opening, coherence, sequencing, ending), framing | lowest: needs explanation + evidence, and agreement is measured |

The PRD says "deterministic checks must be preferred where possible". **Severity** marks what gates: every applicable `critical` check must pass for `technical_gate_passed`. Phase 5 candidates can't be promoted past a failed gate.

## Honest caveats built into the report
- **Caption WER compares two ASR outputs** (source audio vs output audio). It measures *consistency* and catches broken mapping, desync or dropped words. It can't catch a word Whisper got wrong both times ("Paragee"). The check's `explanation` says so.
- **`av_stream_alignment` is a proxy**: it compares stream lengths. It doesn't measure lip-sync offset.
- **Deterministic isn't the same as right.** `frozen_frames` gives the same answer every time, but until `eval-1.2` it was answering the wrong question: it flagged still shots in the *source* (a locked-off moon) as render faults. Now each output freeze is traced back to the source through the timeline, and only freezes the source doesn't explain fail. Found by a Phase 5 experiment (note 19).
- **No calibrated "quality score"**: `pass_rate` is the share of applicable checks passed, labelled uncalibrated (PRD FR-09).

## LLM-as-judge pitfalls (and what we do about them)
| pitfall | mitigation here |
|---|---|
| leniency / self-preference | the judge is told it didn't make the video and must not be generous; it sees only the instructions and the output |
| vague verdicts | structured output: per-requirement `met` + timestamp + evidence; scores per dimension (1–5) |
| inconsistency between runs | measured: re-evaluate the same renders and report agreement (see doc 14) |
| checklist vs holistic disagreement | observed: the instruction judge said 7/7 met while the narrative judge gave sequencing 1/5 on the same video; keep both and don't average them away |
| a judge outage sinks the report | each judge branch catches errors and returns `passed=None` (not applicable) |

## Parallel branches in LangGraph
```
extract_features ─┬─ technical ─┐
                  ├─ temporal ──┤
                  ├─ captions ──┤
                  ├─ style ─────┼─► aggregate
                  ├─ required_content ─┤
                  └─ 3 judges ──┘
```
Several edges out of one node give a **fan-out**: the branches run in the same superstep. They all write to `results: Annotated[list, operator.add]`, so LangGraph *concatenates* their updates instead of overwriting. `aggregate` runs once, after every branch finishes (fan-in).

## Known-defect fixtures
`tests/unit/test_evaluation.py` builds broken videos and asserts the specific check fires, with timestamps: a 2 s black gap at 2.0 s, a 16:9 file, silent audio, 12 s of video against 3 s of audio, out-of-range duration, repeated footage, a cut through "editing", and captions shifted 0.8 s.

## Try this
1. `curl -X POST localhost:8010/renders/<id>/evaluate`, then `GET /edits/<id>/evaluations`. Open `trace_id` in LangSmith and watch the branches run in parallel.
2. `docker compose exec postgres psql -U sivg -c "select check_id, count(*) from evaluation_issues group by 1 order by 2 desc"` shows the most common failures, which is where Phase 5 starts.
3. Add a check (for example "title visible in the first 3 s" via the framing judge) and a defect fixture for it.

## Measured stability (see doc 14)
Deterministic and signal checks reproduce 100% on the same renders. The model judges agree 91.3% overall, and every disagreement came from `visual.framing` (6/23 flips). Treat that judge as advisory until it's made more stable.
