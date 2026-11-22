"""Local filesystem layout for media (PRD: local storage first).

data/projects/<project_id>/assets/<asset_id>/
    source.<ext>        immutable original upload (made read-only)
    derived/            everything we generate: audio.wav, frames/, ...
"""

import uuid
from pathlib import Path

from config.settings import get_settings


def asset_dir(project_id: uuid.UUID, asset_id: uuid.UUID) -> Path:
    return get_settings().data_dir / "projects" / str(project_id) / "assets" / str(asset_id)


def derived_dir(project_id: uuid.UUID, asset_id: uuid.UUID) -> Path:
    d = asset_dir(project_id, asset_id) / "derived"
    d.mkdir(parents=True, exist_ok=True)
    return d
