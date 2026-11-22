# 01 — FFmpeg & ffprobe: the parts this project uses

FFmpeg is the whole video layer here: probing, frame grabs, audio extraction, analysis, and (Phase 2) rendering. Code: `perception/ffmpeg.py`, `perception/video/*`, `perception/audio/*`.

## Mental model
```
inputs (-i files / -f lavfi generators)
   └─► demux ─► decode ─► FILTERGRAPH ─► encode ─► mux ─► output (file, or `-f null -` to discard)
```
- A file holds **streams** (video `v:0`, audio `a:0`, subtitles…). Everything is addressed per stream.
- **Container ≠ codec.** `.mp4`/`.webm` are containers; `h264`, `vp9`, `aac`, `opus` are codecs. Normalising everything to H.264/AAC MP4 (`scripts/fetch_samples.py`) means later stages don't have to care.
- **Filters** transform decoded frames. `-vf`/`-af` = simple chain on one stream; `-filter_complex` = graph with multiple inputs/outputs and labels like `[0:v]`, `[v]`.

## ffprobe → metadata
```bash
ffprobe -v error -print_format json -show_format -show_streams samples/synthetic/cuts.mp4
```
`perception/video/probe.py` reads `format.duration`, the first video stream's `width/height/avg_frame_rate`, and whether an audio stream exists. Gotcha: `avg_frame_rate` is a fraction string like `30000/1001` (= 29.97).

## Seeking: where `-ss` goes matters
- `ffmpeg -ss 12 -i in.mp4 …` (**input seek**): jumps to the nearest keyframe, then decodes to the exact time. Fast and accurate in modern ffmpeg. Used in `frames.py`.
- `ffmpeg -i in.mp4 -ss 12 …` (**output seek**): decodes everything from 0 and discards. Slow, but useful inside complex graphs.

## Analysis filters: decode to nothing, read the log
Many measurements are filters that print to stderr while output goes to `-f null -`:
| Filter | What it tells us | Used in |
|---|---|---|
| `silencedetect=noise=-35dB:d=0.5` | `silence_start` / `silence_end` lines | `audio/silence.py` |
| `ebur128=peak=true` | integrated loudness (LUFS), loudness range, true peak | `audio/loudness.py` |
| `blackdetect` | black segments (Phase 3 evaluator) | — |
| `freezedetect` | frozen frames (Phase 3) | — |

**LUFS** is perceived loudness. Platforms normalise to roughly −14 LUFS (YouTube/Spotify) or −16 LUFS (podcasts), so a −30 LUFS render will sound quiet.

## Generators (`-f lavfi`) = free test footage
`testsrc2`, `smptebars`, `color=c=red`, `mandelbrot`, `sine=frequency=1000`: see `scripts/make_synthetic.py`. Because we control exactly where cuts, black frames and silences are, tests can assert exact timestamps.

## Safety rule
Every command is built as an **argv list** and run without a shell (`subprocess.run([...])`). An LLM never writes an ffmpeg command. It edits a validated `Timeline`, and our own code compiles that into ffmpeg args (Phase 2).

## Try this
1. `ffprobe -v error -show_entries stream=codec_type,codec_name,width,height -of compact samples/synthetic/cuts.mp4`
2. Find the silence yourself: `ffmpeg -i samples/synthetic/silence.mp4 -af silencedetect=noise=-35dB:d=0.5 -f null - 2>&1 | grep silence_`
3. Find the black segment: `ffmpeg -i samples/synthetic/black_gap.mp4 -vf blackdetect=d=0.5 -an -f null - 2>&1 | grep black_`
4. Make a 9:16 crop preview (Phase 2 preview): `ffmpeg -i samples/synthetic/cuts.mp4 -vf "crop=ih*9/16:ih,scale=540:960" -t 5 /tmp/vertical.mp4`

## Text and captions need an ffmpeg built with libass and freetype
The core Homebrew `ffmpeg` here was built without `drawtext` (needs freetype) or `subtitles` / `ass` (need libass). Check yours:
```bash
ffmpeg -hide_banner -filters | grep -E ' (drawtext|subtitles|ass) '
```
This project uses the `homebrew-ffmpeg` tap build, which includes freetype, fontconfig, harfbuzz and libass by default:
```bash
brew uninstall ffmpeg
brew tap homebrew-ffmpeg/ffmpeg
brew trust --formula homebrew-ffmpeg/ffmpeg/ffmpeg   # newer Homebrew requires trusting third-party formulae
brew install homebrew-ffmpeg/ffmpeg/ffmpeg           # builds from source
```
Quick check, which burns a caption into a 9:16 crop:
```bash
printf '1\n00:00:00,500 --> 00:00:03,000\nCaptions work now\n' > /tmp/t.srt
ffmpeg -ss 20 -t 3 -i samples/nasa_interview.mp4 \
  -vf "crop=ih*9/16:ih,scale=540:960,subtitles=/tmp/t.srt:force_style='FontSize=18,Bold=1,Outline=2'" \
  -ss 1.5 -frames:v 1 /tmp/cap.jpg
```
