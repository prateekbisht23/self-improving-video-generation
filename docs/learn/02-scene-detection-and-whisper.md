# 02 — Scene detection (PySceneDetect) & transcription (faster-whisper)

Together these turn a flat video into a **timeline of meaning**: *when do shots change* and *what is said when*. Code: `perception/scene_detection/detect.py`, `perception/audio/transcribe.py`, `perception/context.py`.

## PySceneDetect
`ContentDetector` converts each frame to HSV and scores how much it differs from the previous frame. A score above `threshold` (default 27) means a **cut**.
- Threshold lower → more cuts, including false ones from camera motion or flashes. Higher → misses soft cuts.
- `min_scene_len` stops a burst of flashes from creating dozens of tiny scenes.
- Fades or dissolves are better caught by `AdaptiveDetector` or `ThresholdDetector`, which we can try later.
- No cuts found means we emit one scene covering the whole video, so downstream code never sees an empty list.

The synthetic `cuts.mp4` has cuts at exactly 4 s and 8 s, and `tests/unit/test_scenes.py` checks we find them within ±0.1 s.

## faster-whisper
A CTranslate2 re-implementation of OpenAI Whisper, about 4× faster with less memory. We run `small` with `compute_type="int8"` on the CPU.
- `word_timestamps=True` gives a start and end time for every word. Phase 2 needs this for captions synced to the word.
- `vad_filter=True` runs Silero voice-activity detection first. Whisper tends to *hallucinate* text over silence or music, and VAD removes those regions.
- Model size trade-off: `tiny` / `base` (fast, rough), `small` (our default), `medium` / `large-v3` (better, much slower on CPU).
- `segments` is a **generator**. Transcription actually runs when you iterate over it.

## Joining them: `attach_transcript`
Each scene receives every transcript segment that overlaps its time span, plus `speech_ratio` (the fraction of the scene with speech). That gives the editing agent a simple signal: a scene with high `speech_ratio` carries the message, and one with `speech_ratio` near 0 is b-roll.

## Try this
1. `uv run python -m perception.context samples/synthetic/speech.mp4 -o out/speech.json --no-vision`, then compare the transcript with the sentence in `scripts/make_synthetic.py`.
2. Change `threshold` to 10 and to 60 in `detect_scenes` on a real clip (`samples/nasa_supermoon.mp4`) and count the scenes each time.
3. Set `WHISPER_MODEL=base` in `.env` and compare speed and accuracy.

## What we saw on real footage (120 s cuts)
| Clip | Scenes | Transcript segments | Notes |
|---|---|---|---|
| `nasa_interview` | 7 | 15 | Question slates come out as `speech_ratio=0.00`, answers at about 0.9. That's a free structure signal. |
| `nasa_supermoon` | 10 | 54 | The first "scene" is 0–32 s long: it's made of dissolves that `ContentDetector` misses. `AdaptiveDetector` is a Phase 1 follow-up. |

Implementation notes:
- We pass Whisper a numpy array decoded from our own 16 kHz WAV (`load_wav_16k_mono`), so it never uses PyAV to decode. This avoids a PyAV API mismatch.
- On macOS you may see `objc: Class AVF... is implemented in both cv2/... and av/...`. OpenCV and PyAV each bundle their own copy of the ffmpeg libraries. The warning is harmless for our usage.
- Whisper mishears proper nouns ("Paragee" for *perigee*, "Rilogy" for *Trilogy*). Phase 3's caption-accuracy evaluator (WER) will measure this. Passing an `initial_prompt` with domain words is the usual fix.
