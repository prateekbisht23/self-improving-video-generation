# 12 — Reference style profiles

Code: `perception/style.py`; built through `POST /assets/{id}/style-profile`.

## Measured vs observed
| Kind | Fields | Source |
|---|---|---|
| **Measured** (reproducible) | shot-length distribution (median, p10, p90, cuts/min), pace, words/min, speech coverage, loudness, silence ratio, brightness, saturation and warmth | scene boundaries, transcript words, ebur128, pixel statistics (OpenCV HSV) |
| **Observed** (model) | captions present/position/caps, other on-screen text, transitions, framing, narrative beats | one vision call on a 12-frame **contact sheet** + transcript excerpt |

Observed fields record `observed_by` (the model id) and `evidence_frames` (the timestamps shown), so you can check what the model saw.

`guidance` turns the profile into editing defaults: target shot length (median, clamped to 1.2–6 s), max shot length (p90), caption position and caps, colour preset, and transition type. The planner sees it as a style guide, and the instructions win if they conflict.

## Does the reference change the edit? One honest comparison
Same instruction and footage (supermoon, 20–28 s); reference = the lightning explainer (median shot 0.9 s, fast):

| | clips | median clip | longest clip | colour |
|---|---|---|---|---|
| without reference | 4 | 6.8 s | 10.5 s | vivid |
| with reference | 5 | 4.7 s | 6.8 s | none (matches reference) |

The reference pushed the edit toward shorter shots, but not to 1.2 s. Narration cut on sentence boundaries can't go that short, so jump cuts or b-roll would be needed. This is **n = 1 per condition**: it shows influence, not an effect size. Phase 3's benchmark (5 reference-style tasks) is where this gets measured properly.

## Caveat found
The 0.9 s median is partly an artefact: `AdaptiveDetector` over-splits animated graphics into many short "shots". A style extractor is only as good as the shot detector under it, which is a candidate for an evaluator against hand-labelled cuts.
