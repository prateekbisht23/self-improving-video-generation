"""Deterministic test clips built entirely with ffmpeg (+ macOS `say` for speech).

    uv run python scripts/make_synthetic.py [--out samples/synthetic]

Produces:
  cuts.mp4        3 visually distinct 4s shots (known cut points at 4s and 8s), 1 kHz tone
  black_gap.mp4   2s colour, 2s BLACK, 2s colour  (blackdetect fixture)
  silence.mp4     tone 0-2s, SILENCE 2-5s, tone 5-7s  (silencedetect fixture)
  speech.mp4      spoken sentence over a test pattern (whisper fixture; macOS only)
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from perception.ffmpeg import ffmpeg  # noqa: E402

V = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30"]
A = ["-c:a", "aac", "-ar", "44100"]


def cuts(out: Path) -> None:
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
        "-f", "lavfi", "-i", "color=c=red:size=1280x720:rate=30:duration=4",
        "-f", "lavfi", "-i", "mandelbrot=size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=12",
        "-filter_complex", "[2:v]trim=duration=4,setpts=PTS-STARTPTS[m];[0:v][1:v][m]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-map", "3:a", *V, *A, "-shortest", str(out))


def black_gap(out: Path) -> None:
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=blue:size=1280x720:rate=30:duration=2",
        "-f", "lavfi", "-i", "color=c=black:size=1280x720:rate=30:duration=2",
        "-f", "lavfi", "-i", "color=c=green:size=1280x720:rate=30:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-map", "3:a", *V, *A, str(out))


def silence(out: Path) -> None:
    # volume filter with a time expression mutes 2s..5s
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=7",
        "-f", "lavfi", "-i", "sine=frequency=600:duration=7",
        "-af", "volume=enable='between(t,2,5)':volume=0", *V, *A, str(out))


def speech(out: Path, tmp: Path) -> bool:
    if not shutil.which("say"):
        print("  skip speech.mp4 (no `say`)")
        return False
    aiff = tmp / "speech.aiff"
    subprocess.run(["say", "-o", str(aiff),
                    "Welcome to the editing lab. Today we test scene detection and speech "
                    "transcription. Every word should have a timestamp."], check=True)
    ffmpeg("-f", "lavfi", "-i", "smptebars=size=1280x720:rate=30", "-i", str(aiff),
           *V, *A, "-shortest", str(out))
    aiff.unlink()
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="samples/synthetic")
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in [("cuts", cuts), ("black_gap", black_gap), ("silence", silence)]:
        fn(out / f"{name}.mp4")
        print(f"  wrote {out / name}.mp4")
    if speech(out / "speech.mp4", out):
        print(f"  wrote {out}/speech.mp4")


if __name__ == "__main__":
    main()
