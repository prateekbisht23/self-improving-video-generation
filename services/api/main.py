"""API entrypoint. Phase 0: health only."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

from config.settings import get_settings

app = FastAPI(title="Self-Improving Video Editing Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])

_engine = create_engine(get_settings().database_url, pool_pre_ping=True)


@app.get("/health")
def health() -> dict:
    try:
        with _engine.connect() as c:
            c.execute(text("select 1"))
        db = "ok"
    except Exception as e:  # report, don't crash the health check
        db = f"error: {type(e).__name__}"
    return {"status": "ok", "db": db}
