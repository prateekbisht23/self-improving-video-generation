"""Download licensed sample footage listed in samples/manifest.yaml and normalise it.

    uv run python scripts/fetch_samples.py [--only nasa_interview]

Each clip is trimmed to `max_seconds` (PRD: 30-120s sources) and transcoded to a
consistent H.264/AAC MP4 at 30 fps so every later stage sees the same kind of input.
Originals stay in samples/raw/ untouched (PRD: source media is immutable).
"""

import argparse
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from perception.ffmpeg import ffmpeg  # noqa: E402

UA = "sivg-sample-fetcher/0.1 (educational video-editing research project)"


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  cached {dest.name}")
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, headers={"User-Agent": UA}, follow_redirects=True,
                      timeout=httpx.Timeout(60, read=120)) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {dest.name}: {done / total:5.1%}", end="", flush=True)
    print()
    tmp.rename(dest)


def normalise(src: Path, dst: Path, max_seconds: float) -> None:
    ffmpeg("-i", str(src), "-t", str(max_seconds),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(dst))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    manifest = yaml.safe_load((ROOT / "samples" / "manifest.yaml").read_text())
    raw = ROOT / "samples" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for clip in manifest["clips"]:
        if args.only and clip["id"] not in args.only:
            continue
        print(f"{clip['id']}  [{clip['license']}]")
        src = raw / f"{clip['id']}{Path(clip['url']).suffix}"
        download(clip["url"], src)
        dst = ROOT / "samples" / f"{clip['id']}.mp4"
        if not dst.exists():
            normalise(src, dst, clip.get("max_seconds", 120))
        print(f"  -> {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
