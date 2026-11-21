import pytest

from perception.audio.extract import extract_audio
from perception.audio.transcribe import transcribe

pytestmark = pytest.mark.slow  # needs the whisper model (downloads ~480 MB on first run)


def test_transcribes_synthetic_speech(synthetic, tmp_path):
    if not (synthetic / "speech.mp4").exists():
        pytest.skip("speech fixture needs macOS `say`")
    segs, lang = transcribe(extract_audio(synthetic / "speech.mp4", tmp_path / "a.wav"))
    text = " ".join(s.text for s in segs).lower()
    assert lang == "en"
    assert "editing lab" in text and "timestamp" in text
    words = [w for s in segs for w in s.words]
    assert words and all(w.start <= w.end for w in words)
    assert [w.start for w in words] == sorted(w.start for w in words)
