# 10 — Rendering with ffmpeg filtergraphs

Code: `rendering/ffmpeg/render.py`, `rendering/ass.py`. Every render directory contains `graph.txt`, `overlay.ass` and `timeline.json`. Open them; they are the best way to learn this.

## The shape of a render
```
-ss IN -t DUR -i src   (per clip; seeking before -i is fast and frame-accurate)
[0:v] setpts, crop 9:16 window at crop_x, scale 1080x1920, colour look, fps, format, settb [v0]
[0:a] asetpts, aresample 48k, stereo, volume [a0]
...
cut:        [v0][a0][v1][a1] concat=n=2:v=1:a=1 [jv1][ja1]
transition: [jv1][v2] xfade=transition=fade:duration=0.35:offset=<acc_dur − 0.35> [jv2]
            [ja1][a2] acrossfade=d=0.35 [ja2]
[jv2] subtitles=filename=overlay.ass [vout]
[ja2] loudnorm=I=-14:TP=-1.5:LRA=11 [aout]
```
Key ideas:
- **Labels** like `[v0]` are named pads that connect filters. `;` separates chains.
- **`xfade` needs an `offset`**: the time in the *accumulated* output where the fade starts. That's why the compiler tracks `acc_dur`.
- **Both xfade inputs must match** in size, fps, pixel format *and* timebase, hence `fps`, `format` and `settb=AVTB` on every clip.
- **Crop expressions** are evaluated per input: `w='trunc(min(iw\,ih*1080/1920)/2)*2'` is the widest 9:16 window that fits, rounded to an even number (H.264 needs even dimensions). The `\,` escapes a comma inside an expression.
- **No shell, no escaping.** The graph goes in a file (`-/filter_complex graph.txt`), and ffmpeg runs in the render directory, so `subtitles=filename=overlay.ass` needs no path escaping.

## Captions with ASS + libass
ASS subtitles define **styles** (font, size, outline, alignment, margins) in a coordinate space (`PlayResX/Y` = 1080×1920) and **events** (`Dialogue:` lines with start and end times). Alignment uses numpad layout: 2 = bottom-centre, 8 = top-centre. Colours are `&HAABBGGRR`, so the byte order is reversed. Bottom captions sit 17% up from the bottom, above the area where platform UI covers the video.

## Loudness: one pass is not enough
Single-pass `loudnorm` adapts gain dynamically and **undershoots on short programmes**: our first render came out at −15.9 LUFS against a −14 target. The renderer now measures the output and, if it's off by more than 0.7 LU, applies one linear `volume` correction plus a limiter, with the video stream copied (`-c:v copy`). Result: −14.2 LUFS.

## Reproducibility
`compile_timeline` is a pure function of the timeline. The render records argv, sha256 of the filtergraph and ASS, the timeline hash, and the renderer and ffmpeg versions. `test_edit_session_end_to_end` re-renders a version and asserts that the filtergraph hash and argv are identical.

## Try this
1. `cat data/projects/<p>/edits/<s>/v*/*/graph.txt` and match each line to a clip.
2. Change a transition to `wipeleft` or `slideup` with a manual action, re-render, and watch it.
3. Edit `overlay.ass` by hand (Fontsize, Alignment=8) and re-run the saved argv from `GET /renders/<id>` in that directory.
