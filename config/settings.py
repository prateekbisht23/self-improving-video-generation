"""Central settings, loaded from environment / .env."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # models
    model_planner: str = "ollama:qwen3:8b"
    model_vision: str = "ollama:qwen2.5vl:7b"
    model_judge: str = "ollama:qwen3:8b"
    model_embeddings: str = "google_genai:gemini-embedding-001"
    embedding_dim: int = 768
    ollama_base_url: str = "http://localhost:11434"
    whisper_model: str = "small"
    # client-side requests/minute cap per model (0 = unlimited). Gemini free tier: 15 RPM.
    model_rpm: int = 0

    # infra
    database_url: str = "postgresql+psycopg://sivg:sivg@localhost:5433/sivg"
    redis_url: str = "redis://localhost:6380/0"
    data_dir: Path = Path("data")

    # ingestion limits (PRD: 30-120s sources; allow some headroom, reject the absurd)
    max_upload_mb: int = 1024
    min_duration_s: float = 1.0
    max_duration_s: float = 600.0
    allowed_extensions: tuple[str, ...] = (".mp4", ".mov", ".m4v", ".webm", ".mkv")

    # pipeline switches (tests turn off the paid/slow stages)
    pipeline_vision: bool = True
    pipeline_embeddings: bool = True
    auto_evaluate: bool = True  # evaluate every agent render in a separate job
    rq_sync: bool = False  # run jobs inline instead of via a worker (tests/debugging)


@lru_cache
def get_settings() -> Settings:
    # Also export .env into os.environ: provider SDKs (GOOGLE_API_KEY, ANTHROPIC_API_KEY) and
    # LangSmith (LANGSMITH_*) read the process environment, not our Settings object.
    # Real environment variables still win (override=False).
    load_dotenv(override=False)
    return Settings()
