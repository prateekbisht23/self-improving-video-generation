"""Single entry point for every model the system uses.

Roles (planner / vision / judge) map to `provider:model` strings in settings, so swapping
Ollama for a hosted provider is a config change, never a code change (PRD constraint 8).
"""

from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from config.settings import get_settings

Role = Literal["planner", "vision", "judge"]


def get_chat_model(role: Role, **overrides) -> BaseChatModel:
    s = get_settings()
    spec: str = getattr(s, f"model_{role}")
    provider, _, model = spec.partition(":")
    kwargs: dict = {"temperature": 0.0 if role == "judge" else 0.2}
    if provider == "ollama":
        kwargs["base_url"] = s.ollama_base_url
        # qwen3 "thinking" output breaks structured parsing; keep it off for app calls.
        kwargs["reasoning"] = False
    kwargs.update(overrides)
    return init_chat_model(model, model_provider=provider, **kwargs)
