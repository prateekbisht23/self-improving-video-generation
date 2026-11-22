"""Single entry point for every model the system uses.

Roles (planner / vision / judge) map to `provider:model` strings in settings, so swapping
Ollama for a hosted provider is a config change, never a code change (PRD constraint 8).
"""

from functools import lru_cache
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter

from config.settings import get_settings

Role = Literal["planner", "vision", "judge", "improver"]


@lru_cache
def _rate_limiter(spec: str, rpm: int) -> InMemoryRateLimiter:
    """One token bucket per model per process. Provider quotas are per model, so roles that
    share a model (planner + vision) share a bucket. max_bucket_size=1 means no bursts."""
    return InMemoryRateLimiter(requests_per_second=rpm / 60, check_every_n_seconds=0.1, max_bucket_size=1)


def get_chat_model(role: Role, **overrides) -> BaseChatModel:
    s = get_settings()
    spec: str = getattr(s, f"model_{role}") or s.model_planner
    if s.model_rpm > 0:
        overrides.setdefault("rate_limiter", _rate_limiter(spec, s.model_rpm))
    provider, _, model = spec.partition(":")
    kwargs: dict = {"temperature": 0.0 if role == "judge" else 0.2}
    if provider == "ollama":
        kwargs["base_url"] = s.ollama_base_url
        # qwen3 "thinking" output breaks structured parsing; keep it off for app calls.
        kwargs["reasoning"] = False
    else:
        # hosted APIs: fail fast instead of hanging, retry transient 429/503s with backoff
        kwargs |= {"timeout": 60, "max_retries": 3}
    kwargs.update(overrides)
    return init_chat_model(model, model_provider=provider, **kwargs)


def get_embeddings():
    """Text embedding model (scene search, later failure clustering)."""
    s = get_settings()
    provider, _, model = s.model_embeddings.partition(":")
    if provider == "google_genai":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        # Matryoshka embeddings: 768 of 3072 dims keeps quality and fits pgvector's HNSW limit.
        return GoogleGenerativeAIEmbeddings(model=model, output_dimensionality=s.embedding_dim)
    from langchain.embeddings import init_embeddings

    return init_embeddings(model, provider=provider)


def model_id(role: str) -> str:
    """The exact provider:model string used, recorded next to every generated artefact."""
    s = get_settings()
    return getattr(s, f"model_{role}") or s.model_planner
