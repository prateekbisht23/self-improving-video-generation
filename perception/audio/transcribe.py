"""Local speech-to-text with faster-whisper (word-level timestamps)."""

from functools import lru_cache
from pathlib import Path

from config.settings import get_settings
from perception.schemas import TranscriptSegment, Word


@lru_cache
def _model(name: str):
    from faster_whisper import WhisperModel  # heavy import, keep lazy

    # int8 on CPU is the sweet spot on Apple Silicon (no CUDA).
    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe(audio: str | Path, model_name: str | None = None) -> tuple[list[TranscriptSegment], str]:
    model = _model(model_name or get_settings().whisper_model)
    # vad_filter skips non-speech, which reduces hallucinated text over silence/music.
    segments, info = model.transcribe(str(audio), word_timestamps=True, vad_filter=True)
    out = [
        TranscriptSegment(
            start=round(s.start, 3), end=round(s.end, 3), text=s.text.strip(),
            words=[Word(start=round(w.start, 3), end=round(w.end, 3), text=w.word.strip(),
                        probability=round(w.probability, 3)) for w in (s.words or [])],
        )
        for s in segments  # generator: transcription actually runs here
    ]
    return out, info.language
