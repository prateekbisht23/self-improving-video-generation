import pytest
from sqlalchemy import text

from db.session import get_engine


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    """Apply migrations to the test database once per session."""
    from alembic import command
    from alembic.config import Config

    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
    except Exception as e:  # pragma: no cover
        pytest.skip(f"test database unavailable ({e}); run `docker compose up -d`")
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean_db():
    yield
    with get_engine().begin() as c:
        c.execute(text("TRUNCATE users, projects, media_assets, processing_stages, scenes, transcript_segments, "
                       "editing_sessions, timeline_versions, agent_actions, renders, style_profiles, evaluations, "
                       "evaluation_issues, creator_preferences, preference_events, feedback, memory_confirmations, "
                       "action_predictions, agent_versions, failure_clusters, experiments, promotions "
                       "RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from services.api.main import app

    return TestClient(app)


@pytest.fixture
def project(client):
    return client.post("/projects", json={"title": "Test project"}).json()


def upload(client, project_id, path, kind="source"):
    with open(path, "rb") as f:
        return client.post(f"/projects/{project_id}/assets", files={"file": (path.name, f, "video/mp4")},
                           data={"kind": kind})
