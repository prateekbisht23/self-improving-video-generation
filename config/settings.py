"""Central settings, loaded from environment / .env."""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    model_planner: str = "ollama:qwen3:8b"
    model_vision: str = "ollama:qwen2.5vl:7b"
    model_judge: str = "ollama:qwen3:8b"
    model_embeddings: str = "ollama:nomic-embed-text"
    ollama_base_url: str = "http://localhost:11434"
    whisper_model: str = "small"

    database_url: str = "postgresql+psycopg://sivg:sivg@localhost:5433/sivg"
    redis_url: str = "redis://localhost:6380/0"


@lru_cache
def get_settings() -> Settings:
    # Also export .env into os.environ: provider SDKs (GOOGLE_API_KEY, ANTHROPIC_API_KEY) and
    # LangSmith (LANGSMITH_*) read the process environment, not our Settings object.
    # Real environment variables still win (override=False).
    load_dotenv(override=False)
    return Settings()
