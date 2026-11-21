from pathlib import Path

from perception.ffmpeg import ffmpeg


def extract_audio(video: str | Path, out: str | Path, sample_rate: int = 16000) -> Path:
    """Mono 16 kHz PCM WAV — the format Whisper models expect."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-i", str(video), "-vn", "-ac", "1", "-ar", str(sample_rate),
           "-c:a", "pcm_s16le", str(out))
    return out
