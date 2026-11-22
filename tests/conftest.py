import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Test configuration must be in the environment before config.settings is imported anywhere.
os.environ.update({
    "DATABASE_URL": "postgresql+psycopg://sivg:sivg@localhost:5433/sivg_test",
    "RQ_SYNC": "true",                 # jobs run inline, same code path as the worker
    "PIPELINE_VISION": "false",        # no paid/slow model calls in tests
    "PIPELINE_EMBEDDINGS": "false",
    "LANGSMITH_TRACING": "false",
    "DATA_DIR": tempfile.mkdtemp(prefix="sivg-test-data-"),
    "MIN_DURATION_S": "1",
})

import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "samples" / "synthetic"


@pytest.fixture(scope="session")
def synthetic() -> Path:
    if not (SYN / "cuts.mp4").exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_synthetic.py"),
                        "--out", str(SYN)], check=True)
    return SYN
