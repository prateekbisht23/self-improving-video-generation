"""Staged, resumable media-analysis pipeline (PRD FR-02/FR-03, Phase 1).

    probe -> scenes -> audio -> transcript -> frames -> visual -> index

Rules that make retries safe:
1. Each stage commits its results in its own transaction, then marks itself `done`.
   A crash mid-stage leaves earlier stages untouched (FR-03: failures don't corrupt
   completed stages).
2. A re-run skips `done` stages, so a retry resumes at the failed stage.
3. Stages are idempotent: they replace (delete+insert) their own outputs, never append.
4. Per-scene stages (visual, index) only process scenes still missing output, so a
   rate-limited model call that fails on scene 7 resumes at scene 7.
5. `force_from=<stage>` resets that stage and everything after it for deliberate re-runs.
"""

import logging
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import version

from sqlalchemy import delete, select

from config.models import get_embeddings, model_id
from config.settings import get_settings
from db.models import (
    AssetStatus,
    MediaAsset,
    ProcessingStage,
    Scene,
    StageStatus,
    TranscriptSegment,
)
from db.session import session_scope
from perception.audio.extract import extract_audio
from perception.audio.loudness import measure_loudness
from perception.audio.silence import detect_silence
from perception.context import speech_in_span
from perception.scene_detection.detect import DETECTOR_VERSION, detect_scenes
from perception.video.frames import extract_frame
from perception.video.probe import probe
from services.storage import derived_dir

log = logging.getLogger("pipeline")

StageFn = Callable[[uuid.UUID, bool], dict | None]


def _asset(s, asset_id) -> MediaAsset:
    a = s.get(MediaAsset, asset_id)
    if a is None:
        raise LookupError(f"asset {asset_id} not found")
    return a


# ---------------------------------------------------------------- stages
def stage_probe(asset_id, force):
    with session_scope() as s:
        a = _asset(s, asset_id)
        m = probe(a.storage_path)
        if not m.has_video:
            raise ValueError("file has no video stream")
        a.duration, a.width, a.height, a.fps = m.duration, m.width, m.height, m.fps
        a.aspect_ratio, a.has_audio, a.probe = m.aspect_ratio, m.has_audio, m.model_dump()
        return {"duration": m.duration, "resolution": f"{m.width}x{m.height}", "fps": m.fps}


def stage_scenes(asset_id, force):
    with session_scope() as s:
        a = _asset(s, asset_id)
        found = detect_scenes(a.storage_path, duration=a.duration, fps=a.fps)
        s.execute(delete(Scene).where(Scene.asset_id == a.id))
        s.add_all(Scene(asset_id=a.id, index=sc.index, start=sc.start, end=sc.end) for sc in found)
        return {"scenes": len(found), "tool_version": DETECTOR_VERSION}


def stage_audio(asset_id, force):
    with session_scope() as s:
        a = _asset(s, asset_id)
        if not a.has_audio:
            a.audio_features = None
            return {"skipped": "no audio stream"}
        wav = extract_audio(a.storage_path, derived_dir(a.project_id, a.id) / "audio.wav")
        silences = detect_silence(wav, duration=a.duration)
        a.audio_features = {**measure_loudness(wav), "silences": [x.model_dump() for x in silences]}
        return {"lufs": a.audio_features["integrated_lufs"], "silences": len(silences)}


def stage_transcript(asset_id, force):
    from perception.audio.transcribe import transcribe  # heavy import; worker-only

    with session_scope() as s:
        a = _asset(s, asset_id)
        s.execute(delete(TranscriptSegment).where(TranscriptSegment.asset_id == a.id))
        segs, lang = [], None
        if a.has_audio:
            asr = f"faster-whisper-{get_settings().whisper_model}"
            segs, lang = transcribe(derived_dir(a.project_id, a.id) / "audio.wav")
            s.add_all(TranscriptSegment(asset_id=a.id, start=x.start, end=x.end, text=x.text,
                                        words=[w.model_dump() for w in x.words], asr_model=asr)
                      for x in segs)
        a.language = lang
        for sc in a.scenes:  # denormalise speech onto scenes
            hits, sc.speech_ratio = speech_in_span(sc.start, sc.end, segs)
            sc.transcript_text = " ".join(h.text for h in hits) or None
        return {"segments": len(segs), "language": lang,
                "tool_version": f"faster-whisper {version('faster-whisper')}"}


def stage_frames(asset_id, force):
    with session_scope() as s:
        a = _asset(s, asset_id)
        out = derived_dir(a.project_id, a.id) / "frames"
        for sc in a.scenes:
            mid = sc.start + (sc.end - sc.start) / 2
            sc.frame_path = str(extract_frame(a.storage_path, mid, out / f"scene_{sc.index:03d}.jpg"))
        return {"frames": len(a.scenes)}


def stage_visual(asset_id, force):
    """One model call per scene, committed per scene so partial progress survives failures."""
    from perception.models.describe import describe_frame

    with session_scope() as s:
        ids = s.scalars(select(Scene.id).where(Scene.asset_id == asset_id).order_by(Scene.index)).all()
        if force:
            for sc in s.scalars(select(Scene).where(Scene.asset_id == asset_id)):
                sc.description, sc.tags, sc.vision_model = None, [], None
    done = 0
    for sid in ids:
        with session_scope() as s:
            sc = s.get(Scene, sid)
            if sc.description:
                continue
            d = describe_frame(sc.frame_path, sc.transcript_text)
            sc.description, sc.tags = d.description, [t.lower()[:64] for t in d.tags][:12]
            sc.vision_model = model_id("vision")
            done += 1
    return {"described": done, "tool_version": model_id("vision")}


def scene_search_text(sc: Scene) -> str:
    parts = [sc.description or "", " ".join(sc.tags or []), sc.transcript_text or ""]
    return "\n".join(p for p in parts if p)


def stage_index(asset_id, force):
    """Refresh full-text search text for every scene; embed scenes missing a vector."""
    use_vectors = get_settings().pipeline_embeddings
    with session_scope() as s:
        scenes = s.scalars(select(Scene).where(Scene.asset_id == asset_id).order_by(Scene.index)).all()
        for sc in scenes:
            sc.search_text = scene_search_text(sc)
        todo = [sc for sc in scenes if use_vectors and (force or sc.embedding is None)]
        if todo:
            vecs = get_embeddings().embed_documents([sc.search_text or "(empty scene)" for sc in todo],
                                                    task_type="RETRIEVAL_DOCUMENT")
            for sc, v in zip(todo, vecs, strict=True):
                sc.embedding, sc.embedding_model = v, model_id("embeddings")
        return {"indexed": len(scenes), "embedded": len(todo),
                "tool_version": model_id("embeddings") if use_vectors else "fulltext-only"}


STAGES: list[tuple[str, StageFn]] = [
    ("probe", stage_probe),
    ("scenes", stage_scenes),
    ("audio", stage_audio),
    ("transcript", stage_transcript),
    ("frames", stage_frames),
    ("visual", stage_visual),
    ("index", stage_index),
]
STAGE_NAMES = [n for n, _ in STAGES]


def _enabled(name: str) -> bool:
    return not (name == "visual" and not get_settings().pipeline_vision)


# ---------------------------------------------------------------- orchestration
def ensure_stages(asset_id: uuid.UUID, force_from: str | None = None) -> None:
    if force_from and force_from not in STAGE_NAMES:
        raise ValueError(f"unknown stage {force_from!r}; expected one of {STAGE_NAMES}")
    reset = set(STAGE_NAMES[STAGE_NAMES.index(force_from):]) if force_from else set()
    with session_scope() as s:
        existing = {st.name: st for st in s.scalars(
            select(ProcessingStage).where(ProcessingStage.asset_id == asset_id))}
        for pos, name in enumerate(STAGE_NAMES):
            st = existing.get(name)
            if st is None:
                s.add(ProcessingStage(asset_id=asset_id, name=name, position=pos))
            elif name in reset:
                st.status, st.error, st.detail = StageStatus.pending, None, None


def _set_stage(asset_id, name, **fields) -> None:
    with session_scope() as s:
        st = s.scalar(select(ProcessingStage).where(ProcessingStage.asset_id == asset_id,
                                                    ProcessingStage.name == name))
        for k, v in fields.items():
            setattr(st, k, v)


def _set_asset(asset_id, **fields) -> None:
    with session_scope() as s:
        a = _asset(s, asset_id)
        for k, v in fields.items():
            setattr(a, k, v)


def run_pipeline(asset_id: uuid.UUID | str, force_from: str | None = None,
                 stage_fns: dict[str, StageFn] | None = None) -> dict:
    """Run all pending stages for one asset. Raises on failure (so RQ can retry)."""
    asset_id = uuid.UUID(str(asset_id))
    fns = dict(STAGES) | (stage_fns or {})
    ensure_stages(asset_id, force_from)
    forced = set(STAGE_NAMES[STAGE_NAMES.index(force_from):]) if force_from else set()
    _set_asset(asset_id, status=AssetStatus.processing, last_error=None)

    with session_scope() as s:
        status = {st.name: st.status for st in s.scalars(
            select(ProcessingStage).where(ProcessingStage.asset_id == asset_id))}
    summary = {}
    for name in STAGE_NAMES:
        if status[name] == StageStatus.done:
            summary[name] = "cached"
            continue
        if not _enabled(name):
            _set_stage(asset_id, name, status=StageStatus.skipped, detail={"reason": "disabled"})
            summary[name] = "skipped"
            continue
        with session_scope() as s:
            st = s.scalar(select(ProcessingStage).where(ProcessingStage.asset_id == asset_id,
                                                        ProcessingStage.name == name))
            st.status, st.attempts = StageStatus.running, st.attempts + 1
            st.started_at, st.error = datetime.now(UTC), None
        t0 = time.perf_counter()
        log.info("asset %s: %s ...", asset_id, name)
        try:
            detail = fns[name](asset_id, name in forced) or {}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            _set_stage(asset_id, name, status=StageStatus.failed, finished_at=datetime.now(UTC),
                       error=err + "\n" + traceback.format_exc(limit=5)[-3000:])
            _set_asset(asset_id, status=AssetStatus.failed, last_error=f"[{name}] {err}"[:2000])
            log.exception("asset %s: stage %s failed", asset_id, name)
            raise
        detail["seconds"] = round(time.perf_counter() - t0, 2)
        _set_stage(asset_id, name, status=StageStatus.done, finished_at=datetime.now(UTC),
                   detail=detail, tool_version=detail.pop("tool_version", None))
        summary[name] = detail
        log.info("asset %s: %s done %s", asset_id, name, detail)

    _set_asset(asset_id, status=AssetStatus.ready)
    return summary
