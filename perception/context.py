"""Build a MediaContext for one video: probe -> scenes -> audio -> transcript -> visuals.

    uv run python -m perception.context samples/clip.mp4 -o out/context.json [--no-vision]
"""

import argparse
import logging
import time
from pathlib import Path

from perception.audio.extract import extract_audio
from perception.audio.loudness import measure_loudness
from perception.audio.silence import detect_silence
from perception.audio.transcribe import transcribe
from perception.scene_detection.detect import detect_scenes
from perception.schemas import AudioFeatures, MediaContext, Scene, TranscriptSegment
from perception.video.frames import extract_frame
from perception.video.probe import probe

log = logging.getLogger("perception")


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def attach_transcript(scenes: list[Scene], segments: list[TranscriptSegment]) -> None:
    """Give each scene the transcript segments that overlap it, plus its speech coverage."""
    for sc in scenes:
        sc.transcript = [seg for seg in segments if _overlap(sc.start, sc.end, seg.start, seg.end) > 0]
        spoken = sum(_overlap(sc.start, sc.end, s.start, s.end) for s in sc.transcript)
        sc.speech_ratio = round(spoken / sc.duration, 3) if sc.duration > 0 else 0.0


def build_context(video: str | Path, workdir: str | Path, *, vision: bool = True) -> MediaContext:
    video, workdir = Path(video), Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    def step(name):
        log.info("▶ %s", name)
        return time.perf_counter()

    t = step("probe")
    meta = probe(video)
    log.info("  %.1fs %sx%s @%sfps audio=%s (%.2fs)", meta.duration, meta.width, meta.height,
             meta.fps, meta.has_audio, time.perf_counter() - t)

    t = step("scene detection")
    scenes = detect_scenes(video, duration=meta.duration)
    log.info("  %d scenes (%.2fs)", len(scenes), time.perf_counter() - t)

    audio = AudioFeatures()
    segments: list[TranscriptSegment] = []
    language = None
    if meta.has_audio:
        t = step("audio: extract + silence + loudness")
        wav = extract_audio(video, workdir / "audio.wav")
        audio = AudioFeatures(**measure_loudness(wav),
                              silences=detect_silence(wav, duration=meta.duration))
        log.info("  %s LUFS, %d silences (%.2fs)", audio.integrated_lufs, len(audio.silences),
                 time.perf_counter() - t)

        t = step("transcription (faster-whisper)")
        segments, language = transcribe(wav)
        log.info("  %d segments, lang=%s (%.2fs)", len(segments), language, time.perf_counter() - t)

    attach_transcript(scenes, segments)

    t = step("frames" + (" + vision descriptions" if vision else ""))
    for sc in scenes:
        mid = sc.start + sc.duration / 2
        sc.frame_path = str(extract_frame(video, mid, workdir / "frames" / f"{sc.id}.jpg"))
        if vision:
            from perception.models.describe import describe_frame

            hint = " ".join(s.text for s in sc.transcript) or None
            d = describe_frame(sc.frame_path, hint)
            sc.description, sc.tags = d.description, [x.lower() for x in d.tags]
            log.info("  %s [%.1f-%.1f] %s", sc.id, sc.start, sc.end, sc.description)
    log.info("  done (%.2fs)", time.perf_counter() - t)

    return MediaContext(metadata=meta, audio=audio, transcript=segments, scenes=scenes,
                        language=language)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default="out/context.json")
    ap.add_argument("--no-vision", action="store_true", help="skip LLM frame descriptions")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    out = Path(args.out)
    ctx = build_context(args.video, out.parent / Path(args.video).stem, vision=not args.no_vision)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ctx.model_dump_json(indent=2))
    log.info("wrote %s", out)


if __name__ == "__main__":
    main()
