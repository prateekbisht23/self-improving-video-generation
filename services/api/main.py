"""API entrypoint:  uv run uvicorn services.api.main:app --port 8010"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config.settings import get_settings
from db.session import get_engine
from services.api.routes import assets, edits, memory, projects, search

get_settings()  # export .env for SDKs used in request handlers (embeddings for search)

app = FastAPI(title="Self-Improving Video Editing Agent", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(projects.router)
app.include_router(assets.router)
app.include_router(search.router)
app.include_router(edits.router)
app.include_router(memory.router)


@app.get("/health")
def health() -> dict:
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
        db = "ok"
    except Exception as e:  # report, don't crash the health check
        db = f"error: {type(e).__name__}"
    return {"status": "ok", "db": db}
