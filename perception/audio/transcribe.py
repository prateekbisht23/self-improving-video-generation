"""Local speech-to-text with faster-whisper (word-level timestamps)."""

import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

from config.settings import get_settings
from perception.schemas import TranscriptSegment, Word


@lru_cache
def _model(name: str):
    from faster_whisper import WhisperModel  # heavy import, keep lazy

    # int8 on CPU is the sweet spot on Apple Silicon (no CUDA).
    return WhisperModel(name, device="cpu", compute_type="int8")


def load_wav_16k_mono(path: str | Path) -> np.ndarray:
    """Read the PCM WAV written by `extract_audio` into float32 [-1, 1].

    We decode with ffmpeg ourselves, so whisper gets a ready array and never touches PyAV.
    """
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16 kHz mono s16 WAV (use extract_audio)")
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0


def transcribe(audio: str | Path, model_name: str | None = None) -> tuple[list[TranscriptSegment], str]:
    model = _model(model_name or get_settings().whisper_model)
    # vad_filter skips non-speech, which reduces hallucinated text over silence/music.
    segments, info = model.transcribe(load_wav_16k_mono(audio), word_timestamps=True, vad_filter=True)
    out = [
        TranscriptSegment(
            start=round(s.start, 3), end=round(s.end, 3), text=s.text.strip(),
            words=[Word(start=round(w.start, 3), end=round(w.end, 3), text=w.word.strip(),
                        probability=round(w.probability, 3)) for w in (s.words or [])],
        )
        for s in segments  # generator: transcription actually runs here
    ]
    return out, info.language
