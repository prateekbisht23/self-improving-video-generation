"""Run an editing session: DB -> EditContext -> editing graph -> versions/actions/renders in DB."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from agent.graphs.editing_graph import AGENT_VERSION, agent_config, run_edit
from agent.runtime import EditDeps
from config.settings import get_settings
from db.models import (
    AgentAction,
    AssetStatus,
    EditingSession,
    MediaAsset,
    Render,
    RenderStatus,
    Scene,
    SessionStatus,
    StyleProfile,
    TimelineVersion,
    TranscriptSegment,
)
from db.session import session_scope
from editing.context import EditContext, SceneInfo, WordT
from editing.timeline.schema import AssetRef, Timeline
from perception.style import EXTRACTOR_VERSION, build_profile

log = logging.getLogger("editing")


# ------------------------------------------------------------------ context
def load_edit_context(s, asset_ids: list[uuid.UUID], project_id: uuid.UUID) -> EditContext:
    assets = [s.get(MediaAsset, a) for a in asset_ids]
    for a in assets:
        if a is None or a.status != AssetStatus.ready:
            raise ValueError(f"asset {a.id if a else '?'} is not ready for editing")
    refs = [AssetRef(id=str(a.id), path=a.storage_path, duration=a.duration, width=a.width, height=a.height,
                     has_audio=bool(a.has_audio)) for a in assets]
    scenes: dict[str, SceneInfo] = {}
    by_db: dict[uuid.UUID, str] = {}
    words: dict[str, list[WordT]] = {}
    n = 0
    for a in assets:
        segs = s.scalars(select(TranscriptSegment).where(TranscriptSegment.asset_id == a.id)
                         .order_by(TranscriptSegment.start)).all()
        words[str(a.id)] = [WordT(w["start"], w["end"], w["text"]) for g in segs for w in (g.words or [])]
        for sc in s.scalars(select(Scene).where(Scene.asset_id == a.id).order_by(Scene.index)):
            n += 1
            sid = f"S{n}"
            by_db[sc.id] = sid
            scenes[sid] = SceneInfo(
                sid=sid, db_id=str(sc.id), asset_id=str(a.id), index=sc.index, start=sc.start, end=sc.end,
                description=sc.description or "", tags=list(sc.tags or []), transcript=sc.transcript_text or "",
                speech_ratio=sc.speech_ratio,
                segments=[(g.start, g.end, g.text) for g in segs if g.end > sc.start and g.start < sc.end])

    def search(query: str, k: int) -> list[SceneInfo]:
        from services.api.routes.search import keyword_search, rrf, semantic_search

        with session_scope() as s2:
            lists = {"keyword": keyword_search(s2, project_id, query, k * 4)}
            if get_settings().pipeline_embeddings:
                lists["semantic"] = semantic_search(s2, project_id, query, k * 4)
            hits = [sc for sc, _, _ in rrf(lists) if sc.id in by_db]
            return [scenes[by_db[sc.id]] for sc in hits[:k]]

    return EditContext(assets=refs, scenes=scenes, words=words, search=search)


# ------------------------------------------------------------------ recorder
class DbRecorder:
    def __init__(self, session_id: uuid.UUID):
        self.session_id = session_id
        self._version_ids: dict[int, uuid.UUID] = {}

    def save_plan(self, plan: dict) -> None:
        with session_scope() as s:
            s.get(EditingSession, self.session_id).plan = plan

    def save_version(self, timeline: Timeline, version: int, created_by: str) -> None:
        with session_scope() as s:
            row = TimelineVersion(session_id=self.session_id, version=version,
                                  parent_id=self._version_ids.get(version - 1),
                                  timeline=timeline.model_dump(mode="json"), content_hash=timeline.content_hash(),
                                  schema_version=timeline.schema_version, created_by=created_by)
            s.add(row)
            s.flush()
            self._version_ids[version] = row.id

    def record_action(self, **f) -> None:
        with session_scope() as s:
            s.add(AgentAction(session_id=self.session_id, **f))

    def render(self, timeline: Timeline, version: int) -> dict:
        return render_version(self._version_ids[version])


def render_version(version_id: uuid.UUID) -> dict:
    """Render a stored timeline version (also used for re-renders: same input -> same output)."""
    from rendering.ffmpeg.render import render

    with session_scope() as s:
        v = s.get(TimelineVersion, version_id)
        sess = v.session
        tl = Timeline.model_validate(v.timeline)
        out_dir = (get_settings().data_dir / "projects" / str(sess.project_id) / "edits" / str(sess.id)
                   / f"v{v.version:03d}" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f"))
    try:
        r = render(tl, out_dir)
    except Exception as e:
        with session_scope() as s:
            s.add(Render(timeline_version_id=version_id, status=RenderStatus.failed, error=str(e)[:4000]))
        raise
    with session_scope() as s:
        row = Render(timeline_version_id=version_id, status=RenderStatus.done, path=r.path, duration=r.duration,
                     meta=r.to_dict())
        s.add(row)
        s.flush()
        return {"render_id": str(row.id), "path": r.path, "duration": r.duration, "seconds": r.seconds}


# ------------------------------------------------------------------ style profiles
def ensure_style_profile(asset_id: uuid.UUID) -> dict:
    """Build (or reuse) the style profile of a processed reference asset."""
    with session_scope() as s:
        existing = s.scalar(select(StyleProfile).where(StyleProfile.asset_id == asset_id,
                                                       StyleProfile.version == EXTRACTOR_VERSION))
        if existing:
            return existing.profile
        a = s.get(MediaAsset, asset_id)
        if a is None or a.status != AssetStatus.ready:
            raise ValueError(f"reference asset {asset_id} is not ready")
        scenes = a.scenes
        segs = a.transcript
        af = a.audio_features or {}
        args = dict(
            duration=a.duration, aspect_ratio=a.aspect_ratio, spans=[(x.start, x.end) for x in scenes],
            frames=[(round(x.start + (x.end - x.start) / 2, 2), x.frame_path) for x in scenes if x.frame_path],
            words=[(w["start"], w["end"], w["text"]) for g in segs for w in (g.words or [])],
            lufs=af.get("integrated_lufs"), silences=[(x["start"], x["end"]) for x in af.get("silences", [])],
            transcript_text=" ".join(g.text for g in segs))
    profile = build_profile(**args, use_model=get_settings().pipeline_vision).model_dump()
    with session_scope() as s:
        s.add(StyleProfile(asset_id=asset_id, version=EXTRACTOR_VERSION, profile=profile))
    return profile


# ------------------------------------------------------------------ job
def run_editing_session(session_id: str) -> dict:
    sid = uuid.UUID(session_id)
    with session_scope() as s:
        sess = s.get(EditingSession, sid)
        if sess.versions:  # sessions are single-shot; a retry starts clean
            for v in sess.versions:
                s.delete(v)
            for a in sess.actions:
                s.delete(a)
            s.flush()
        sess.status, sess.error = SessionStatus.running, None
        sess.agent_version, sess.agent_config = AGENT_VERSION, agent_config()
        project_id, instructions = sess.project_id, sess.instructions
        asset_ids = [uuid.UUID(x) for x in sess.source_asset_ids]
        ref_id = sess.reference_asset_id
        c = sess.constraints or {}
        ctx = load_edit_context(s, asset_ids, project_id)
    try:
        style = ensure_style_profile(ref_id) if ref_id else None
        deps = EditDeps(ctx=ctx, recorder=DbRecorder(sid), style=style,
                        memory=list(c.get("preferences", [])))  # Phase 4 replaces with the memory store
        run_id = uuid.uuid4()  # we choose the root run id, so the DB row links to the exact trace
        with session_scope() as s:
            s.get(EditingSession, sid).trace_id = str(run_id)
        final = run_edit(instructions, deps, min_duration=c.get("min_duration", 15),
                         max_duration=c.get("max_duration", 30), run_id=run_id,
                         metadata={"session_id": session_id, "project_id": str(project_id)})
    except Exception as e:
        with session_scope() as s:
            sess = s.get(EditingSession, sid)
            sess.status, sess.error = SessionStatus.failed, f"{type(e).__name__}: {e}"[:4000]
        raise
    with session_scope() as s:
        sess = s.get(EditingSession, sid)
        if final.get("status") == "rendered":
            sess.status = SessionStatus.rendered
        else:
            sess.status = SessionStatus.failed
            sess.error = "; ".join(final.get("problems") or []) or final.get("last_error") or "agent did not finish"
        steps = s.scalar(select(func.count()).select_from(AgentAction).where(AgentAction.session_id == sid))
    render_id = (final.get("render") or {}).get("render_id")
    if render_id and get_settings().auto_evaluate:
        from services.worker.jobs import enqueue_evaluation

        enqueue_evaluation(render_id)
    return {"status": final.get("status"), "version": final.get("version"), "steps": steps,
            "render_id": render_id, "log": final.get("log", [])}
