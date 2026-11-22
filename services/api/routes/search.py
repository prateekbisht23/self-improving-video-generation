"""Scene search: keyword (Postgres full-text) + semantic (pgvector) fused with RRF."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config.models import get_embeddings
from config.settings import get_settings
from db.models import MediaAsset, Scene
from db.session import get_db
from services.api.routes.projects import get_project
from services.api.schemas import SceneOut, SearchHit

router = APIRouter(tags=["search"])
RRF_K = 60  # standard Reciprocal Rank Fusion constant


def keyword_search(db: Session, project_id: uuid.UUID, q: str, limit: int) -> list[Scene]:
    tsq = func.websearch_to_tsquery("english", q)
    rank = func.ts_rank_cd(Scene.search_tsv, tsq)
    stmt = (select(Scene).join(MediaAsset).where(MediaAsset.project_id == project_id,
                                                 Scene.search_tsv.op("@@")(tsq))
            .order_by(rank.desc()).limit(limit))
    return list(db.scalars(stmt))


def semantic_search(db: Session, project_id: uuid.UUID, q: str, limit: int) -> list[Scene]:
    vec = get_embeddings().embed_query(q, task_type="RETRIEVAL_QUERY")
    stmt = (select(Scene).join(MediaAsset)
            .where(MediaAsset.project_id == project_id, Scene.embedding.is_not(None))
            .order_by(Scene.embedding.cosine_distance(vec)).limit(limit))
    return list(db.scalars(stmt))


def rrf(ranked_lists: dict[str, list[Scene]]) -> list[tuple[Scene, float, list[str]]]:
    """score(d) = sum over lists of 1 / (k + rank). Robust to incomparable score scales."""
    scores: dict[uuid.UUID, float] = {}
    by_id: dict[uuid.UUID, Scene] = {}
    sources: dict[uuid.UUID, list[str]] = {}
    for name, items in ranked_lists.items():
        for rank, sc in enumerate(items, start=1):
            scores[sc.id] = scores.get(sc.id, 0.0) + 1.0 / (RRF_K + rank)
            by_id[sc.id] = sc
            sources.setdefault(sc.id, []).append(name)
    order = sorted(scores, key=scores.get, reverse=True)
    return [(by_id[i], scores[i], sources[i]) for i in order]


@router.get("/projects/{project_id}/search", response_model=list[SearchHit])
def search_scenes(project_id: uuid.UUID, q: str = Query(min_length=1, max_length=500),
                  k: int = Query(5, ge=1, le=50),
                  mode: str = Query("hybrid", pattern="^(hybrid|keyword|semantic)$"),
                  db: Session = Depends(get_db)):
    get_project(project_id, db)
    pool = max(k * 4, 20)
    lists: dict[str, list[Scene]] = {}
    if mode in ("hybrid", "keyword"):
        lists["keyword"] = keyword_search(db, project_id, q, pool)
    if mode in ("hybrid", "semantic") and get_settings().pipeline_embeddings:
        lists["semantic"] = semantic_search(db, project_id, q, pool)
    return [SearchHit(scene=SceneOut.model_validate(sc), score=round(score, 5), matched_by=src)
            for sc, score, src in rrf(lists)[:k]]
