import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "samples" / "synthetic"


@pytest.fixture(scope="session")
def synthetic() -> Path:
    if not (SYN / "cuts.mp4").exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_synthetic.py"),
                        "--out", str(SYN)], check=True)
    return SYN
