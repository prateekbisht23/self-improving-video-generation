"""Upload + processing status + analysis results."""

import hashlib
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import get_settings
from db.models import AssetKind, AssetStatus, MediaAsset, Scene, TranscriptSegment
from db.session import get_db
from perception.ffmpeg import FFmpegError
from perception.schemas import (
    AudioFeatures,
    MediaContext,
    MediaMetadata,
    SilenceRange,
)
from perception.schemas import Scene as SceneSchema
from perception.schemas import TranscriptSegment as SegSchema
from perception.video.probe import probe
from services.api.routes.projects import get_project
from services.api.schemas import AssetDetail, AssetOut, SceneOut, SegmentOut
from services.storage import asset_dir
from services.worker.jobs import enqueue_processing
from services.worker.pipeline import STAGE_NAMES

router = APIRouter(tags=["assets"])
CHUNK = 1 << 20


def _reject(status: int, msg: str, cleanup: Path | None = None):
    if cleanup and cleanup.exists():
        shutil.rmtree(cleanup, ignore_errors=True)
    raise HTTPException(status, msg)


@router.post("/projects/{project_id}/assets", response_model=AssetDetail, status_code=201)
def upload_asset(project_id: uuid.UUID, file: UploadFile = File(...),
                 kind: AssetKind = Form(AssetKind.source), db: Session = Depends(get_db)):
    """Validate, store immutably, enqueue background processing. Returns immediately (NFR-07)."""
    cfg = get_settings()
    project = get_project(project_id, db)
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()
    if ext not in cfg.allowed_extensions:
        _reject(415, f"unsupported file type '{ext or '?'}'; allowed: {', '.join(cfg.allowed_extensions)}")

    asset_id = uuid.uuid4()
    folder = asset_dir(project.id, asset_id)
    folder.mkdir(parents=True)
    dest = folder / f"source{ext}"
    sha, size, limit = hashlib.sha256(), 0, cfg.max_upload_mb * 1024 * 1024
    with dest.open("wb") as out:  # stream: never hold a whole video in memory
        while chunk := file.file.read(CHUNK):
            size += len(chunk)
            if size > limit:
                _reject(413, f"file exceeds {cfg.max_upload_mb} MB limit", folder)
            sha.update(chunk)
            out.write(chunk)
    if size == 0:
        _reject(422, "empty file", folder)

    try:  # content validation: extension alone proves nothing
        meta: MediaMetadata = probe(dest)
    except FFmpegError:
        _reject(422, "file is not a readable video (ffprobe could not parse it)", folder)
    if not meta.has_video:
        _reject(422, "file has no video stream", folder)
    if not (cfg.min_duration_s <= meta.duration <= cfg.max_duration_s):
        _reject(422, f"duration {meta.duration:.1f}s outside allowed "
                     f"{cfg.min_duration_s:.0f}-{cfg.max_duration_s:.0f}s", folder)
    os.chmod(dest, 0o444)  # source media is immutable

    asset = MediaAsset(id=asset_id, project_id=project.id, kind=kind, original_filename=name,
                       storage_path=str(dest), sha256=sha.hexdigest(), size_bytes=size,
                       status=AssetStatus.uploaded)
    db.add(asset)
    db.commit()  # the worker must be able to see the row
    enqueue_processing(asset.id)
    db.refresh(asset)
    return asset


def _get_asset(asset_id: uuid.UUID, db: Session) -> MediaAsset:
    a = db.get(MediaAsset, asset_id)
    if a is None:
        raise HTTPException(404, f"asset {asset_id} not found")
    return a


@router.get("/assets/{asset_id}", response_model=AssetDetail)
def read_asset(asset_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_asset(asset_id, db)


@router.post("/assets/{asset_id}/process", response_model=AssetOut, status_code=202)
def reprocess(asset_id: uuid.UUID, force_from: str | None = Query(None, pattern="^(" + "|".join(STAGE_NAMES) + ")$"),
              db: Session = Depends(get_db)):
    """Retry (resumes at the failed stage) or force a re-run from a given stage."""
    a = _get_asset(asset_id, db)
    if a.status in (AssetStatus.queued, AssetStatus.processing):
        raise HTTPException(409, f"asset is already {a.status}")
    enqueue_processing(a.id, force_from)
    db.refresh(a)
    return a


@router.get("/assets/{asset_id}/scenes", response_model=list[SceneOut])
def list_scenes(asset_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_asset(asset_id, db)
    return db.scalars(select(Scene).where(Scene.asset_id == asset_id).order_by(Scene.index)).all()


@router.get("/assets/{asset_id}/transcript", response_model=list[SegmentOut])
def transcript(asset_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_asset(asset_id, db)
    return db.scalars(select(TranscriptSegment).where(TranscriptSegment.asset_id == asset_id)
                      .order_by(TranscriptSegment.start)).all()


@router.get("/assets/{asset_id}/context", response_model=MediaContext)
def media_context(asset_id: uuid.UUID, db: Session = Depends(get_db)):
    """The full structured context, rebuilt from the DB alone (no source file needed)."""
    a = _get_asset(asset_id, db)
    if a.status != AssetStatus.ready:
        raise HTTPException(409, f"asset is {a.status}, not ready")
    segs = [SegSchema(start=t.start, end=t.end, text=t.text, words=t.words or []) for t in a.transcript]
    af = a.audio_features or {}
    return MediaContext(
        metadata=MediaMetadata.model_validate(a.probe),
        audio=AudioFeatures(integrated_lufs=af.get("integrated_lufs"),
                            loudness_range_lu=af.get("loudness_range_lu"),
                            true_peak_dbfs=af.get("true_peak_dbfs"),
                            silences=[SilenceRange(**x) for x in af.get("silences", [])]),
        transcript=segs,
        scenes=[SceneSchema(id=str(sc.id), index=sc.index, start=sc.start, end=sc.end,
                            frame_path=sc.frame_path, description=sc.description, tags=sc.tags or [],
                            speech_ratio=sc.speech_ratio,
                            transcript=[g for g in segs if g.end > sc.start and g.start < sc.end])
                for sc in a.scenes],
        language=a.language,
    )
